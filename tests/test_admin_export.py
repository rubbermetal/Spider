import re
import csv
import io
import json
from spiderlib import db

def add(admin_db, url, status="done", **cols):
    conn = db.connect(admin_db)
    cursor = conn.cursor()
    cols["host"] = "a.com"
    cols["added_at"] = db.now()
    cols["url"] = url
    cols["status"] = status
    cursor.execute("INSERT INTO urls (host, added_at, url, status, hidden, approved, title) VALUES (?, ?, ?, ?, ?, ?, ?)",
                   (cols["host"], cols["added_at"], cols["url"], cols["status"], cols.get("hidden", 0), cols.get("approved", 0), cols.get("title", "")))
    conn.commit()
    conn.close()

def test_requires_login(admin_client):
    response = admin_client.get("/export")
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]

    response = admin_client.get("/export/download")
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]

def test_export_page(client, admin_db):
    add(admin_db, "http://a.com/1", hidden=1)
    add(admin_db, "http://a.com/2")

    response = client.get("/export")
    assert response.status_code == 200
    assert "Export" in response.get_data(as_text=True)
    assert "1 URL(s) match" in response.get_data(as_text=True)
    assert "Download" in response.get_data(as_text=True)
    assert "Update count" in response.get_data(as_text=True)
    assert "Approved only" in response.get_data(as_text=True)

    response = client.get("/export?hidden=include")
    assert response.status_code == 200
    assert "2 URL(s) match" in response.get_data(as_text=True)

    response = client.get("/export?format=xml")
    assert response.status_code == 200
    assert "format must be csv or json" in response.get_data(as_text=True)

def test_download_csv(client, admin_db):
    add(admin_db, "http://a.com/1", title="One", approved=1)
    add(admin_db, "http://a.com/2", title="Two")

    response = client.get("/export/download")
    assert response.status_code == 200
    assert response.headers["Content-Type"].startswith("text/csv")
    assert response.headers["Content-Type"].count("utf-8") == 1
    assert 'attachment; filename="spider-urls-' in response.headers["Content-Disposition"]
    assert response.headers["Content-Disposition"].endswith('.csv"')

    reader = csv.DictReader(io.StringIO(response.get_data(as_text=True)))
    rows = list(reader)
    assert len(rows) == 2

    response = client.get("/export/download?approved=only")
    reader = csv.DictReader(io.StringIO(response.get_data(as_text=True)))
    rows = list(reader)
    assert len(rows) == 1

def test_download_json(client, admin_db):
    response = client.get("/export/download?format=json&status=done")
    assert response.status_code == 200
    assert response.headers["Content-Type"].startswith("application/json")
    data = json.loads(response.get_data(as_text=True))
    assert isinstance(data, list)
    for entry in data:
        assert "url" in entry
        assert "approved" in entry

def test_download_hidden_toggle(client, admin_db):
    add(admin_db, "http://a.com/1", hidden=1)

    response = client.get("/export/download")
    reader = csv.DictReader(io.StringIO(response.get_data(as_text=True)))
    rows = list(reader)
    assert len(rows) == 0

    response = client.get("/export/download?hidden=include")
    reader = csv.DictReader(io.StringIO(response.get_data(as_text=True)))
    rows = list(reader)
    assert len(rows) == 1

def test_download_errors(client):
    response = client.get("/export/download?format=pdf")
    assert response.status_code == 400
    assert "format must be csv or json" in response.get_data(as_text=True)

    response = client.get("/export/download?status=nope")
    assert response.status_code == 400

def test_download_is_read_only_get(client):
    response = client.get("/export")
    match = re.search(r'name="csrf" value="([^"]+)"', response.get_data(as_text=True))
    csrf_token = match.group(1)

    response = client.post("/export/download", data={"csrf": csrf_token})
    assert response.status_code == 405
