"""Regression checks for the team's notification-only @here policy (stdlib runner)."""
import unittest
from plugins.platforms.discord import adapter as a


class HerePayloadTests(unittest.TestCase):
    def test_notification_has_one_here_and_no_other_live_mentions(self):
        text, kwargs = a._team_notification_payload(
            '@here <@100000000000000001> approval: @everyone and @here <@&123>',
            enabled=True, notify=True,
        )
        self.assertTrue(text.startswith('@here\n'))
        self.assertEqual(text.count('@here'), 1)
        self.assertNotIn('@everyone', text)
        self.assertNotIn('<@100000000000000001>', text)
        mentions = kwargs['allowed_mentions']
        self.assertTrue(mentions.everyone)
        self.assertFalse(mentions.users)
        self.assertFalse(mentions.roles)
        self.assertFalse(mentions.replied_user)


class ScopeTests(unittest.TestCase):
    def test_long_notifications_are_not_truncated(self):
        text, _ = a._team_notification_payload('x' * 6000, enabled=True, notify=True)
        self.assertEqual(text.count('x'), 6000)

    def test_ordinary_and_quoted_text_stay_unpinged(self):
        for text in ('ordinary reply', 'Quoted: @here hello', '```\n@here hello\n```', '@hereafter'):
            self.assertEqual(a._team_notification_payload(text, enabled=True), (text, {}))

    def test_disabled_policy_preserves_content(self):
        self.assertEqual(a._team_notification_payload('@here hi', enabled=False, notify=True), ('@here hi', {}))

    def test_leading_here_is_an_explicit_notification(self):
        text, kwargs = a._team_notification_payload('@here hello @everyone @here', enabled=True)
        self.assertEqual(text.count('@here'), 1)
        self.assertNotIn('@everyone', text)
        self.assertTrue(kwargs['allowed_mentions'].everyone)


from types import SimpleNamespace
from unittest.mock import AsyncMock


def make_adapter():
    adapter = object.__new__(a.DiscordAdapter)
    adapter.config = SimpleNamespace(extra={'team_notification_here': True})
    adapter.platform = SimpleNamespace(value='discord')
    adapter._client = object()
    channel = SimpleNamespace(send=AsyncMock(return_value=SimpleNamespace(id=1)))
    adapter._resolve_channel = AsyncMock(return_value=channel)
    adapter._is_forum_parent = lambda channel: False
    adapter._reply_reference_for_send = lambda *args: None
    adapter._reply_to_mode = 'off'
    adapter._last_self_message_id = {}
    adapter._nonconversational_messages = SimpleNamespace(mark_many=AsyncMock())
    adapter._record_response_async = AsyncMock(side_effect=lambda reply, result, *args: result)
    adapter._last_overflow_preview = {}
    adapter.format_message = lambda text: text
    adapter._allowed_user_ids = {'100000000000000001'}
    adapter._allowed_role_ids = set()
    return adapter, channel


class SendRouteTests(unittest.IsolatedAsyncioTestCase):
    async def test_cron_notification_pings_here_not_owner(self):
        adapter, channel = make_adapter()
        result = await adapter.send('99', '<@100000000000000001> report @everyone', metadata={'job_id':'hourly', 'notify':True})
        self.assertTrue(result.success)
        payload = channel.send.call_args.kwargs
        self.assertTrue(payload['content'].startswith('@here\n'))
        self.assertNotIn('@everyone', payload['content'])
        self.assertNotIn('<@100000000000000001>', payload['content'])
        self.assertTrue(payload['allowed_mentions'].everyone)
        self.assertFalse(payload['allowed_mentions'].users)

    async def test_normal_final_reply_does_not_broadcast(self):
        adapter, channel = make_adapter()
        result = await adapter.send('99', 'normal reply', metadata={'notify':True})
        self.assertTrue(result.success)
        self.assertNotIn('allowed_mentions', channel.send.call_args.kwargs)
        self.assertEqual(channel.send.call_args.kwargs['content'], 'normal reply')


class PromptRouteTests(unittest.IsolatedAsyncioTestCase):
    async def test_exec_approval_notifies_here_and_preserves_allowlist(self):
        adapter, channel = make_adapter()
        result = await adapter.send_exec_approval('99', 'echo @everyone', 'session', description='review')
        self.assertTrue(result.success)
        payload = channel.send.call_args.kwargs
        self.assertTrue(payload['content'].startswith('@here\n'))
        self.assertNotIn('@everyone', payload['content'])
        self.assertFalse(payload['allowed_mentions'].users)
        self.assertEqual(payload['view'].allowed_user_ids, {'100000000000000001'})

    async def test_clarify_notifies_here(self):
        adapter, channel = make_adapter()
        result = await adapter.send_clarify('99', '@everyone Choose one?', None, 'clarify', 'session')
        self.assertTrue(result.success)
        self.assertTrue(channel.send.call_args.kwargs['content'].startswith('@here\n'))
        self.assertNotIn('@everyone', channel.send.call_args.kwargs['content'])


class AdditionalRouteTests(unittest.IsolatedAsyncioTestCase):
    async def test_stream_edit_neutralizes_body_mentions(self):
        adapter, channel = make_adapter()
        msg = SimpleNamespace(edit=AsyncMock())
        channel.get_partial_message = lambda message_id: msg
        result = await adapter.edit_message('99', '1', '@here review @everyone <@123>', finalize=True)
        self.assertTrue(result.success)
        payload = msg.edit.call_args.kwargs
        self.assertNotIn('@everyone', payload['content'])
        self.assertFalse(payload['allowed_mentions'].users)

    async def test_long_cron_content_preserved_and_single_ping(self):
        adapter, channel = make_adapter()
        content = 'x' * 6000 + ' @everyone @here'
        result = await adapter.send('99', content, metadata={'job_id':'report'})
        self.assertTrue(result.success)
        payloads = [c.kwargs for c in channel.send.call_args_list]
        self.assertEqual(sum(p['content'].count('@here') for p in payloads), 1)
        self.assertEqual(sum(p['content'].count('x') for p in payloads), 6000)
        self.assertFalse(any('@everyone' in p['content'] for p in payloads))

    async def test_long_prompts_remain_within_discord_limit(self):
        for kind in ('exec', 'clarify'):
            adapter, channel = make_adapter()
            if kind == 'exec':
                result = await adapter.send_exec_approval('99', 'x' * 6000, 'session', description='review')
            else:
                result = await adapter.send_clarify('99', 'x' * 6000, None, 'clarify', 'session')
            self.assertTrue(result.success)
            self.assertLessEqual(len(channel.send.call_args.kwargs['content']), 2000)

    async def test_forum_cron_notification(self):
        adapter, channel = make_adapter()
        adapter._is_forum_parent = lambda channel: True
        channel.create_thread = AsyncMock(return_value=SimpleNamespace(id=42, send=AsyncMock()))
        result = await adapter.send('99', 'report @everyone', metadata={'job_id':'report'})
        self.assertTrue(result.success)
        payload = channel.create_thread.call_args.kwargs
        self.assertTrue(payload['content'].startswith('@here\n'))
        self.assertNotIn('@everyone', payload['content'])
        self.assertFalse(payload['allowed_mentions'].users)


class OverflowRouteTests(unittest.IsolatedAsyncioTestCase):
    async def test_final_stream_overflow_keeps_broadcasts_neutralized(self):
        adapter, channel = make_adapter()
        channel.id = 99
        adapter._message_reference_from_ids = lambda *args: None
        msg = SimpleNamespace(edit=AsyncMock())
        channel.get_partial_message = lambda message_id: msg
        result = await adapter.edit_message('99', '1', '@here ' + 'x' * 5500 + ' @everyone @here', finalize=True)
        self.assertTrue(result.success)
        payloads = [c.kwargs for c in msg.edit.call_args_list + channel.send.call_args_list]
        self.assertFalse(any('@everyone' in p['content'] for p in payloads))
        self.assertEqual(sum(p['content'].count('@here') for p in payloads), 1)
        self.assertTrue(all(not p['allowed_mentions'].users for p in payloads))


class SilentTests(unittest.IsolatedAsyncioTestCase):
    def test_leading_silent_line_drops_here_and_silences(self):
        self.assertEqual(a._team_notification_payload('@silent\n**Account usage**', enabled=True, notify=True,
                                                      can_silence=True), ('**Account usage**', {'silent': True}))
        # edits can't be silenced: the line still goes, nothing else is added
        self.assertEqual(a._team_notification_payload('@silent\nx', enabled=True, notify=True), ('x', {}))
        # honoured with the @here policy off too
        self.assertEqual(a._team_notification_payload('@silent\nx', enabled=False, can_silence=True), ('x', {'silent': True}))

    def test_silent_only_as_a_standalone_first_line(self):
        self.assertEqual(a._team_notification_payload('@silent **Account usage**\n- x', enabled=True, notify=True,
                                                      can_silence=True), ('**Account usage**\n- x', {'silent': True}))
        for text in ('@silently here', 'note: @silent\nx', 'x\n@silent'):
            self.assertEqual(a._team_notification_payload(text, enabled=True, can_silence=True), (text, {}))

    async def test_silent_cron_send(self):
        adapter, channel = make_adapter()
        result = await adapter.send('99', '@silent **Account usage**\n- Codex weekly: 40%', metadata={'job_id': 'hourly'})
        self.assertTrue(result.success)
        payload = channel.send.call_args.kwargs
        self.assertEqual(payload['content'], '**Account usage**\n- Codex weekly: 40%')
        self.assertTrue(payload['silent'])
        self.assertNotIn('allowed_mentions', payload)

    async def test_silent_forum_send(self):
        adapter, channel = make_adapter()
        adapter._is_forum_parent = lambda channel: True
        channel.create_thread = AsyncMock(return_value=SimpleNamespace(id=42, send=AsyncMock()))
        result = await adapter.send('99', '@silent\nreport', metadata={'job_id': 'report'})
        self.assertTrue(result.success)
        self.assertTrue(channel.create_thread.call_args.kwargs['silent'])
        self.assertNotIn('@here', channel.create_thread.call_args.kwargs['content'])

    def test_cron_does_not_swallow_inline_silent(self):
        # the scheduler runs this matcher before the adapter: a lone "@silent" line means "post nothing"
        from gateway.response_filters import is_autonomous_silence_response
        self.assertFalse(is_autonomous_silence_response('@silent **Account usage**\n- Codex weekly: 40%'))
        self.assertTrue(is_autonomous_silence_response('@silent\n**Account usage**'))


if __name__ == '__main__':
    unittest.main()
