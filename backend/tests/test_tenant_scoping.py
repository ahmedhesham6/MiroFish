"""
Tests confirming tenant isolation in ReportManager and TaskManager.
"""

import os
import json
import tempfile
import pytest

from app.models.task import Task, TaskManager, TaskStatus
from datetime import datetime


# ============================================================
# TaskManager tests
# ============================================================

class TestTaskManagerTenantScoping:
    """TaskManager must not leak tasks across tenants."""

    def setup_method(self):
        """Reset singleton state between tests."""
        mgr = TaskManager()
        with mgr._task_lock:
            mgr._tasks.clear()

    def test_create_and_get_own_task(self):
        mgr = TaskManager()
        task_id = mgr.create_task(tenant_id="tenant_A", task_type="report_generate")
        task = mgr.get_task("tenant_A", task_id)
        assert task is not None
        assert task.task_id == task_id
        assert task.tenant_id == "tenant_A"

    def test_cross_tenant_get_returns_none(self):
        mgr = TaskManager()
        task_id = mgr.create_task(tenant_id="tenant_A", task_type="report_generate")
        # tenant_B must not see tenant_A's task
        task = mgr.get_task("tenant_B", task_id)
        assert task is None

    def test_list_tasks_only_own_tenant(self):
        mgr = TaskManager()
        mgr.create_task(tenant_id="tenant_A", task_type="t1")
        mgr.create_task(tenant_id="tenant_A", task_type="t2")
        mgr.create_task(tenant_id="tenant_B", task_type="t3")

        a_tasks = mgr.list_tasks("tenant_A")
        b_tasks = mgr.list_tasks("tenant_B")

        assert len(a_tasks) == 2
        assert len(b_tasks) == 1
        assert all(t["tenant_id"] == "tenant_A" for t in a_tasks)
        assert all(t["tenant_id"] == "tenant_B" for t in b_tasks)

    def test_list_tasks_filter_by_type(self):
        mgr = TaskManager()
        mgr.create_task(tenant_id="tenant_A", task_type="report_generate")
        mgr.create_task(tenant_id="tenant_A", task_type="graph_build")

        report_tasks = mgr.list_tasks("tenant_A", task_type="report_generate")
        assert len(report_tasks) == 1
        assert report_tasks[0]["task_type"] == "report_generate"

    def test_task_to_dict_includes_tenant_id(self):
        mgr = TaskManager()
        task_id = mgr.create_task(tenant_id="tenant_X", task_type="simulation_prepare")
        task = mgr.get_task("tenant_X", task_id)
        d = task.to_dict()
        assert d["tenant_id"] == "tenant_X"


# ============================================================
# ReportManager tests
# ============================================================

class TestReportManagerTenantScoping:
    """ReportManager must read/write under tenant-scoped directories."""

    def test_get_reports_dir_is_tenant_scoped(self, tmp_path, monkeypatch):
        """_get_reports_dir must return a path under the tenant's data dir."""
        from app.services.report_agent import ReportManager
        from app.models.tenant import TenantManager

        monkeypatch.setattr(
            TenantManager,
            "_get_tenant_data_dir",
            staticmethod(lambda tid: str(tmp_path / tid))
        )

        dir_a = ReportManager._get_reports_dir("tenant_A")
        dir_b = ReportManager._get_reports_dir("tenant_B")

        assert "tenant_A" in dir_a
        assert "tenant_B" in dir_b
        assert dir_a != dir_b

    def test_save_and_get_report_scoped_to_tenant(self, tmp_path, monkeypatch):
        """save_report writes under tenant dir; get_report only reads from same tenant."""
        from app.services.report_agent import ReportManager, Report, ReportStatus
        from app.models.tenant import TenantManager

        monkeypatch.setattr(
            TenantManager,
            "_get_tenant_data_dir",
            staticmethod(lambda tid: str(tmp_path / tid))
        )

        report = Report(
            report_id="report_001",
            simulation_id="sim_001",
            graph_id="graph_001",
            simulation_requirement="test req",
            status=ReportStatus.COMPLETED,
            outline=None,
            markdown_content="# Test",
            created_at="2026-01-01T00:00:00",
            completed_at="2026-01-01T01:00:00",
        )

        ReportManager.save_report("tenant_A", report)

        # tenant_A can read it
        loaded = ReportManager.get_report("tenant_A", "report_001")
        assert loaded is not None
        assert loaded.report_id == "report_001"

        # tenant_B cannot read it
        not_found = ReportManager.get_report("tenant_B", "report_001")
        assert not_found is None

    def test_list_reports_only_own_tenant(self, tmp_path, monkeypatch):
        """list_reports must only return reports belonging to the requesting tenant."""
        from app.services.report_agent import ReportManager, Report, ReportStatus
        from app.models.tenant import TenantManager

        monkeypatch.setattr(
            TenantManager,
            "_get_tenant_data_dir",
            staticmethod(lambda tid: str(tmp_path / tid))
        )

        def make_report(rid, sim_id):
            return Report(
                report_id=rid,
                simulation_id=sim_id,
                graph_id="g1",
                simulation_requirement="req",
                status=ReportStatus.COMPLETED,
                outline=None,
                markdown_content="",
                created_at="2026-01-01T00:00:00",
                completed_at="2026-01-01T01:00:00",
            )

        ReportManager.save_report("tenant_A", make_report("r_a1", "sim_a1"))
        ReportManager.save_report("tenant_A", make_report("r_a2", "sim_a2"))
        ReportManager.save_report("tenant_B", make_report("r_b1", "sim_b1"))

        a_reports = ReportManager.list_reports("tenant_A")
        b_reports = ReportManager.list_reports("tenant_B")

        assert len(a_reports) == 2
        assert len(b_reports) == 1
        assert all(r.report_id.startswith("r_a") for r in a_reports)
        assert b_reports[0].report_id == "r_b1"

    def test_delete_report_scoped_to_tenant(self, tmp_path, monkeypatch):
        """delete_report must only delete from the tenant's own directory."""
        from app.services.report_agent import ReportManager, Report, ReportStatus
        from app.models.tenant import TenantManager

        monkeypatch.setattr(
            TenantManager,
            "_get_tenant_data_dir",
            staticmethod(lambda tid: str(tmp_path / tid))
        )

        report = Report(
            report_id="report_del",
            simulation_id="sim_del",
            graph_id="g1",
            simulation_requirement="req",
            status=ReportStatus.COMPLETED,
            outline=None,
            markdown_content="",
            created_at="2026-01-01T00:00:00",
            completed_at="",
        )
        ReportManager.save_report("tenant_A", report)

        # tenant_B delete attempt returns False (report not in B's dir)
        result_b = ReportManager.delete_report("tenant_B", "report_del")
        assert result_b is False

        # report still exists for tenant_A
        assert ReportManager.get_report("tenant_A", "report_del") is not None

        # tenant_A deletes successfully
        result_a = ReportManager.delete_report("tenant_A", "report_del")
        assert result_a is True
        assert ReportManager.get_report("tenant_A", "report_del") is None
