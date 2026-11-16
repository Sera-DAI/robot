import unittest

from robot_agent import application
from robot_agent.adapters.sqs import Message
from robot_agent.application import Deps, cycle, run
from robot_agent.errors import QueueError, ShutdownError

START = 1_000_000_000_000
SHUTDOWN = '{"version": 1, "action": "shutdown"}'


class FakeQueue:
    def __init__(self, batches=(), fail_on_delete=False):
        self.batches, self.deleted, self.fail_on_delete = list(batches), [], fail_on_delete

    def receive(self):
        if not self.batches:
            return []
        batch = self.batches.pop(0)
        if isinstance(batch, Exception):
            raise batch
        return batch

    def delete(self, receipt):
        if self.fail_on_delete:
            raise QueueError("x")
        self.deleted.append(receipt)


def msg(body=SHUTDOWN, receipt="r1", sent=START + 1_000):
    return Message(body=body, receipt=receipt, sent_at_ms=sent)


def build(queue, execute=None, now=START + 2_000):
    executed, sleeps = [], []
    deps = Deps(
        queue=queue,
        execute=execute or executed.append,
        now_ms=lambda: now,
        sleep=sleeps.append,
    )
    return deps, executed, sleeps


class Cycle(unittest.TestCase):
    def test_valid_command_is_deleted_and_executed_once(self):
        queue = FakeQueue([[msg()]])
        d, executed, _ = build(queue)
        self.assertEqual(cycle(d, START), 1)
        self.assertEqual(executed, ["shutdown"])
        self.assertEqual(queue.deleted, ["r1"])

    def test_deletes_before_executing(self):
        order = []
        queue = FakeQueue([[msg()]])
        queue.delete = lambda receipt: order.append("delete")
        d, _, _ = build(queue, execute=lambda action: order.append("execute"))
        cycle(d, START)
        self.assertEqual(order, ["delete", "execute"])

    def test_if_the_delete_fails_it_does_not_execute(self):
        d, executed, _ = build(FakeQueue([[msg()]], fail_on_delete=True))
        with self.assertLogs(application.LOG, level="ERROR"):
            self.assertEqual(cycle(d, START), 0)
        self.assertEqual(executed, [])

    def test_a_strange_message_is_deleted_without_executing(self):
        queue = FakeQueue([[msg(body='{"version": 1, "action": "calc.exe"}'), msg(body="junk", receipt="r2")]])
        d, executed, _ = build(queue)
        with self.assertLogs(application.LOG, level="WARNING") as captured:
            cycle(d, START)
        self.assertEqual(executed, [])
        self.assertEqual(queue.deleted, ["r1", "r2"])
        self.assertNotIn("calc.exe", "\n".join(captured.output))

    def test_a_command_from_before_startup_or_without_a_timestamp_is_deleted_without_executing(self):
        queue = FakeQueue([[msg(sent=START - 5_000), msg(receipt="r2", sent=None)]])
        d, executed, _ = build(queue)
        with self.assertLogs(application.LOG, level="WARNING"):
            cycle(d, START)
        self.assertEqual(executed, [])
        self.assertEqual(queue.deleted, ["r1", "r2"])

    def test_an_old_command_is_deleted_without_executing(self):
        queue = FakeQueue([[msg(sent=START + 1_000)]])
        d, executed, _ = build(queue, now=START + 61_001)
        with self.assertLogs(application.LOG, level="WARNING"):
            cycle(d, START)
        self.assertEqual(executed, [])
        self.assertEqual(queue.deleted, ["r1"])

    def test_a_repeated_command_in_the_batch_executes_once(self):
        queue = FakeQueue([[msg(), msg(receipt="r2")]])
        d, executed, _ = build(queue)
        self.assertEqual(cycle(d, START), 1)
        self.assertEqual(executed, ["shutdown"])
        self.assertEqual(queue.deleted, ["r1", "r2"])

    def test_a_windows_failure_does_not_bring_the_agent_down(self):
        def refuse(action):
            raise ShutdownError("x")

        d, _, _ = build(FakeQueue([[msg()]]), execute=refuse)
        with self.assertLogs(application.LOG, level="ERROR"):
            self.assertEqual(cycle(d, START), 0)


class Run(unittest.TestCase):
    def test_a_queue_error_waits_with_backoff_and_continues(self):
        queue = FakeQueue([QueueError("a"), QueueError("b"), [msg(sent=START + 2_000)]])
        d, executed, sleeps = build(queue)
        rounds = iter([True, True, True, False])
        with self.assertLogs(application.LOG, level="INFO"):
            run(d, keep_going=lambda: next(rounds))
        self.assertEqual(sleeps, [5, 10])
        self.assertEqual(executed, ["shutdown"])

    def test_the_backoff_has_a_ceiling(self):
        queue = FakeQueue([QueueError("x")] * 10)
        d, _, sleeps = build(queue)
        rounds = iter([True] * 10 + [False])
        with self.assertLogs(application.LOG, level="INFO"):
            run(d, keep_going=lambda: next(rounds))
        self.assertEqual(max(sleeps), application.MAX_WAIT_S)


if __name__ == "__main__":
    unittest.main()
