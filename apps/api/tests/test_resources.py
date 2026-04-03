from __future__ import annotations

from pathlib import Path


def test_resources_crud(client):
    # Create course
    res = client.post("/courses", json={"name": "Course for Resources"})
    assert res.status_code == 200
    course_id = res.json()["id"]

    # Create resource metadata
    res = client.post("/resources", json={"course_id": course_id, "title": "Resource 1", "resource_type": "pdf"})
    assert res.status_code == 200
    resource = res.json()
    resource_id = resource["id"]

    # List resources
    res = client.get("/resources", params={"course_id": course_id})
    assert res.status_code == 200
    assert any(r["id"] == resource_id for r in res.json())

    # Update resource
    res = client.patch(f"/resources/{resource_id}", json={"title": "Resource Updated"})
    assert res.status_code == 200
    assert res.json()["title"] == "Resource Updated"

    # Delete
    res = client.delete(f"/resources/{resource_id}")
    assert res.status_code == 200
    assert res.json()["ok"] is True


def test_delete_uploaded_resource_removes_parent_directory(client):
    # Create course first
    res = client.post("/courses", json={"name": "Course Upload Delete"})
    assert res.status_code == 200
    course_id = res.json()["id"]

    # Upload a small text file
    upload = client.post(
        "/resources/upload",
        data={"course_id": course_id, "title": "Upload Me", "resource_type": "file"},
        files={"file": ("hello.txt", b"hello world", "text/plain")},
    )
    assert upload.status_code == 200
    resource = upload.json()
    storage_path = resource["storage_path"]
    assert storage_path

    p = Path(storage_path)
    assert p.exists()
    parent = p.parent
    assert parent.exists()

    # Deleting the resource should remove the per-resource folder.
    deleted = client.delete(f"/resources/{resource['id']}")
    assert deleted.status_code == 200
    assert deleted.json()["ok"] is True
    assert not parent.exists()


def test_upload_batch_returns_accepted_and_rejected_entries(client):
    res = client.post("/courses", json={"name": "Batch Course"})
    assert res.status_code == 200
    course_id = res.json()["id"]

    uploaded = client.post(
        "/resources/upload-batch",
        data={"course_id": course_id, "resource_type": "file"},
        files=[
            ("files", ("ok.txt", b"hello", "text/plain")),
            ("files", ("bad.bin", b"\x00\x01", "application/octet-stream")),
        ],
    )
    assert uploaded.status_code == 200
    rows = uploaded.json()
    assert len(rows) == 2
    accepted = [r for r in rows if r["status"] == "accepted"]
    rejected = [r for r in rows if r["status"] == "rejected"]
    assert len(accepted) == 1
    assert accepted[0]["resource"] is not None
    assert accepted[0]["resource"]["title"] == "ok.txt"
    assert len(rejected) == 1
    assert "unsupported file type" in (rejected[0]["reason"] or "")


def test_resource_diagnostics_exposes_lifecycle_events(client):
    res = client.post("/courses", json={"name": "Diagnostics Course"})
    assert res.status_code == 200
    course_id = res.json()["id"]
    upload = client.post(
        "/resources/upload",
        data={"course_id": course_id, "title": "Diag", "resource_type": "file"},
        files={"file": ("diag.txt", b"diag token", "text/plain")},
    )
    assert upload.status_code == 200
    resource = upload.json()
    diag = client.get(f"/resources/{resource['id']}/diagnostics")
    assert diag.status_code == 200
    body = diag.json()
    assert body["resource"]["id"] == resource["id"]
    assert isinstance(body["events"], list)
    assert len(body["events"]) >= 1
    assert body["events"][0]["event_type"] == "resource.uploaded"
    assert body["summary"]["correlation_id"].startswith("job:")
    assert body["summary"]["resource_id"] == resource["id"]
    assert body["summary"]["current_explanation"]
    assert body["summary"]["latest_job_id"]


def test_reindex_requires_storage_path(client):
    res = client.post("/courses", json={"name": "Reindex Guard Course"})
    assert res.status_code == 200
    course_id = res.json()["id"]
    create = client.post("/resources", json={"course_id": course_id, "title": "No file yet", "resource_type": "file"})
    assert create.status_code == 200
    resource = create.json()
    replay = client.post(f"/resources/{resource['id']}/reindex")
    assert replay.status_code == 409
    assert replay.json()["detail"] == "Resource has no storage_path and cannot be reindexed"


def test_resource_diagnostics_failed_state_exposes_stage_reason_and_context(client, db_session, tmp_path, monkeypatch):
    from app.indexing.pipeline import index_resource
    from app.models.resource import Resource
    from app.models.user import User
    from app.parsing.pdf import PdfParseError

    monkeypatch.setattr(
        "app.indexing.pipeline.extract_pdf_pages",
        lambda _path: (_ for _ in ()).throw(PdfParseError("pdf_parse_error", "operator-facing parse failure")),
    )
    user = User(email="resource-diag-fail@test.dev", name="ResourceDiagFail")
    db_session.add(user)
    db_session.commit()

    broken_pdf = tmp_path / "broken-diagnostic.pdf"
    broken_pdf.write_bytes(b"%PDF broken")
    resource = Resource(
        user_id=user.id,
        course_id=None,
        title="Broken Diagnostic",
        resource_type="file",
        original_filename="broken-diagnostic.pdf",
        mime_type="application/pdf",
        storage_path=str(broken_pdf),
        parse_status="uploaded",
        ocr_status="pending",
        index_status="pending",
        lifecycle_state="uploaded",
    )
    db_session.add(resource)
    db_session.commit()

    index_resource(
        db_session,
        resource_id=str(resource.id),
        trace_context={
            "job_id": "job-resource-fail",
            "worker_id": "worker-diag",
            "attempt": 3,
        },
    )
    diag = client.get(f"/resources/{resource.id}/diagnostics", headers={"X-User-Id": str(user.id)})
    assert diag.status_code == 200
    summary = diag.json()["summary"]
    assert summary["lifecycle_state"] == "failed"
    assert summary["current_stage"] == "parsing"
    assert summary["latest_failure_stage"] == "parsing"
    assert summary["latest_failure_message"] == "operator-facing parse failure"
    assert summary["latest_error_code"] == "pdf_parse_error"
    assert summary["latest_job_id"] == "job-resource-fail"
    assert summary["latest_worker_id"] == "worker-diag"
    assert summary["latest_index_run_id"]
    assert summary["correlation_id"] == "job:job-resource-fail"
    assert "failed during parsing" in summary["current_explanation"]
