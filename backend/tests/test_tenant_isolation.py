"""
Tests for tenant isolation in TaskManager and ReportManager.
Verifies that data is scoped per tenant and not accessible cross-tenant.
"""

import unittest
from datetime import datetime

from app.models.task import TaskManager, TaskStatus


class TestTaskManagerTenantIsolation(unittest.TestCase):
    """TaskManager must scope tasks by tenant_id."""

    def setUp(self):
        # Reset singleton state for clean tests
        TaskManager._instance = None
        self.tm = TaskManager()

    def tearDown(self):
        TaskManager._instance = None

    def test_create_task_stores_tenant_id(self):
        task_id = self.tm.create_task("tn_alice", "test_job")
        task = self.tm.get_task("tn_alice", task_id)
        self.assertIsNotNone(task)
        self.assertEqual(task.tenant_id, "tn_alice")

    def test_get_task_rejects_wrong_tenant(self):
        task_id = self.tm.create_task("tn_alice", "test_job")
        # Bob cannot see Alice's task
        task = self.tm.get_task("tn_bob", task_id)
        self.assertIsNone(task)

    def test_list_tasks_scoped_by_tenant(self):
        self.tm.create_task("tn_alice", "job_a")
        self.tm.create_task("tn_alice", "job_b")
        self.tm.create_task("tn_bob", "job_c")

        alice_tasks = self.tm.list_tasks("tn_alice")
        bob_tasks = self.tm.list_tasks("tn_bob")

        self.assertEqual(len(alice_tasks), 2)
        self.assertEqual(len(bob_tasks), 1)
        self.assertTrue(all(t["tenant_id"] == "tn_alice" for t in alice_tasks))
        self.assertTrue(all(t["tenant_id"] == "tn_bob" for t in bob_tasks))

    def test_list_tasks_filter_by_type(self):
        self.tm.create_task("tn_alice", "graph_build")
        self.tm.create_task("tn_alice", "simulation_prepare")

        graph_tasks = self.tm.list_tasks("tn_alice", task_type="graph_build")
        self.assertEqual(len(graph_tasks), 1)
        self.assertEqual(graph_tasks[0]["task_type"], "graph_build")

    def test_update_task_works(self):
        task_id = self.tm.create_task("tn_alice", "test_job")
        self.tm.update_task(task_id, status=TaskStatus.PROCESSING, progress=50)
        task = self.tm.get_task("tn_alice", task_id)
        self.assertEqual(task.status, TaskStatus.PROCESSING)
        self.assertEqual(task.progress, 50)

    def test_complete_task(self):
        task_id = self.tm.create_task("tn_alice", "test_job")
        self.tm.complete_task(task_id, {"output": "done"})
        task = self.tm.get_task("tn_alice", task_id)
        self.assertEqual(task.status, TaskStatus.COMPLETED)
        self.assertEqual(task.progress, 100)

    def test_fail_task(self):
        task_id = self.tm.create_task("tn_alice", "test_job")
        self.tm.fail_task(task_id, "something broke")
        task = self.tm.get_task("tn_alice", task_id)
        self.assertEqual(task.status, TaskStatus.FAILED)
        self.assertEqual(task.error, "something broke")

    def test_cleanup_preserves_active_tasks(self):
        task_id = self.tm.create_task("tn_alice", "active_job")
        self.tm.update_task(task_id, status=TaskStatus.PROCESSING)
        self.tm.cleanup_old_tasks(max_age_hours=0)
        # Processing task should survive cleanup
        task = self.tm.get_task("tn_alice", task_id)
        self.assertIsNotNone(task)

    def test_to_dict_includes_tenant_id(self):
        task_id = self.tm.create_task("tn_alice", "test_job")
        task = self.tm.get_task("tn_alice", task_id)
        d = task.to_dict()
        self.assertEqual(d["tenant_id"], "tn_alice")
        self.assertIn("task_id", d)
        self.assertIn("task_type", d)


class TestReportManagerSignatures(unittest.TestCase):
    """Verify ReportManager methods require tenant_id."""

    def test_update_progress_requires_tenant_id(self):
        from app.services.report_agent import ReportManager
        import inspect
        sig = inspect.signature(ReportManager.update_progress)
        params = list(sig.parameters.keys())
        # First param after cls should be tenant_id
        self.assertEqual(params[0], "tenant_id")

    def test_get_progress_requires_tenant_id(self):
        from app.services.report_agent import ReportManager
        import inspect
        sig = inspect.signature(ReportManager.get_progress)
        params = list(sig.parameters.keys())
        self.assertEqual(params[0], "tenant_id")

    def test_get_generated_sections_requires_tenant_id(self):
        from app.services.report_agent import ReportManager
        import inspect
        sig = inspect.signature(ReportManager.get_generated_sections)
        params = list(sig.parameters.keys())
        self.assertEqual(params[0], "tenant_id")

    def test_assemble_full_report_requires_tenant_id(self):
        from app.services.report_agent import ReportManager
        import inspect
        sig = inspect.signature(ReportManager.assemble_full_report)
        params = list(sig.parameters.keys())
        self.assertEqual(params[0], "tenant_id")

    def test_save_report_requires_tenant_id(self):
        from app.services.report_agent import ReportManager
        import inspect
        sig = inspect.signature(ReportManager.save_report)
        params = list(sig.parameters.keys())
        self.assertEqual(params[0], "tenant_id")

    def test_get_report_requires_tenant_id(self):
        from app.services.report_agent import ReportManager
        import inspect
        sig = inspect.signature(ReportManager.get_report)
        params = list(sig.parameters.keys())
        self.assertEqual(params[0], "tenant_id")

    def test_list_reports_requires_tenant_id(self):
        from app.services.report_agent import ReportManager
        import inspect
        sig = inspect.signature(ReportManager.list_reports)
        params = list(sig.parameters.keys())
        self.assertEqual(params[0], "tenant_id")

    def test_delete_report_requires_tenant_id(self):
        from app.services.report_agent import ReportManager
        import inspect
        sig = inspect.signature(ReportManager.delete_report)
        params = list(sig.parameters.keys())
        self.assertEqual(params[0], "tenant_id")


if __name__ == "__main__":
    unittest.main()
