import re
from spiderlib import db

def token(client, path="/seeds"):
    response = client.get(path, follow_redirects=True)
    match = re.search(r'name="csrf" value="([^"]+)"', response.get_data(as_text=True))
    if match:
        return match.group(1)
    return None

def conn_of(admin_db):
    return db.connect(admin_db)

def add(client, url, follow=False, **extra):
    data = {"csrf": token(client), "url": url, **extra}
    return client.post("/seeds/add", data=data, follow_redirects=follow)

def test_seeds_requires_login(admin_client):
    response = admin_client.get("/seeds")
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]

def test_empty_page(client):
    response = client.get("/seeds")
    assert response.status_code == 200
    assert "No seeds yet" in response.get_data(as_text=True)
    assert "Add a seed" in response.get_data(as_text=True)

def test_add_seed(client, admin_db):
    response = add(client, "http://example.com", follow=True, max_depth="2", max_pages="50")
    assert response.status_code == 200
    assert "Seed added." in response.get_data(as_text=True)
    conn = conn_of(admin_db)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM seeds")
    rows = cursor.fetchall()
    assert len(rows) == 1
    assert rows[0]["max_depth"] == 2
    conn.close()

def test_add_invalid(client):
    response = add(client, "not a url")
    assert response.status_code == 400
    assert "not a valid http or https URL" in response.get_data(as_text=True)
    response = add(client, "http://a.com", max_depth="999")
    assert response.status_code == 400
    assert "must be a whole number between 0 and 50" in response.get_data(as_text=True)
    assert "http://a.com" in response.get_data(as_text=True)

def test_add_duplicate(client):
    add(client, "http://example.com")
    response = add(client, "http://example.com")
    assert response.status_code == 400
    assert "seed already exists" in response.get_data(as_text=True)

def test_list_shows_counts_and_actions(client, admin_db):
    add(client, "http://a.com")
    response = client.get("/seeds")
    assert response.status_code == 200
    assert "Disable" in response.get_data(as_text=True)
    assert "Recrawl" in response.get_data(as_text=True)
    assert "Edit" in response.get_data(as_text=True)
    assert "Delete" in response.get_data(as_text=True)

def test_edit_seed(client, admin_db):
    add(client, "http://a.com")
    response = client.get("/seeds/1/edit")
    assert response.status_code == 200
    assert "http://a.com/" in response.get_data(as_text=True)
    data = {
        "csrf": token(client, "/seeds/1/edit"),
        "max_depth": "5",
        "max_pages": "",
        "recrawl_hours": "6",
        "allow_external": "yes"
    }
    response = client.post("/seeds/1/edit", data=data)
    assert response.status_code == 302
    conn = conn_of(admin_db)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM seeds WHERE id = 1")
    row = cursor.fetchone()
    assert row["max_depth"] == 5
    assert row["recrawl_hours"] == 6
    assert row["allow_external"] == 1
    assert row["max_pages"] is None
    conn.close()
    invalid_data = {
        "csrf": token(client, "/seeds/1/edit"),
        "max_depth": "x"
    }
    response = client.post("/seeds/1/edit", data=invalid_data)
    assert response.status_code == 400
    response = client.get("/seeds/999/edit")
    assert response.status_code == 404

def test_toggle(client, admin_db):
    add(client, "http://a.com")
    response = client.post("/seeds/1/toggle", data={"csrf": token(client)})
    assert response.status_code == 302
    conn = conn_of(admin_db)
    cursor = conn.cursor()
    cursor.execute("SELECT enabled FROM seeds WHERE id = 1")
    enabled = cursor.fetchone()[0]
    assert enabled == 0
    response = client.post("/seeds/1/toggle", data={"csrf": token(client)}, follow_redirects=True)
    cursor.execute("SELECT enabled FROM seeds WHERE id = 1")
    enabled = cursor.fetchone()[0]
    assert enabled == 1
    response = client.post("/seeds/999/toggle", data={"csrf": token(client)})
    assert response.status_code == 404
    conn.close()

def test_recrawl(client, admin_db):
    add(client, "http://a.com")
    conn = conn_of(admin_db)
    conn.execute("UPDATE urls SET status = 'done' WHERE url = 'http://a.com/'")
    conn.commit()
    response = client.post("/seeds/1/recrawl", data={"csrf": token(client)}, follow_redirects=True)
    assert response.status_code == 200
    assert "Requeued 1 URL" in response.get_data(as_text=True)
    status = conn.execute("SELECT status FROM urls WHERE url = 'http://a.com/'").fetchone()[0]
    assert status == "queued"
    response = client.post("/seeds/999/recrawl", data={"csrf": token(client)})
    assert response.status_code == 404
    conn.close()

def test_delete_confirm_then_delete(client, admin_db):
    add(client, "http://a.com")
    response = client.get("/seeds/1/delete")
    assert response.status_code == 200
    assert "Delete the seed" in response.get_data(as_text=True)
    assert "Cancel" in response.get_data(as_text=True)
    conn = conn_of(admin_db)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM seeds")
    rows = cursor.fetchall()
    assert len(rows) == 1
    response = client.post("/seeds/1/delete", data={"csrf": token(client)}, follow_redirects=True)
    assert response.status_code == 200
    assert "Seed deleted" in response.get_data(as_text=True)
    cursor.execute("SELECT * FROM seeds")
    rows = cursor.fetchall()
    assert len(rows) == 0
    response = client.get("/seeds/999/delete")
    assert response.status_code == 404
    conn.close()

def test_post_without_csrf_rejected(client):
    response = client.post("/seeds/add", data={"url": "http://a.com"})
    assert response.status_code == 400
    response = client.post("/seeds/1/toggle")
    assert response.status_code == 400

def test_nav_has_seeds_link(client):
    response = client.get("/")
    assert response.status_code == 200
    assert 'href="/seeds"' in response.get_data(as_text=True)


def test_seeds_page_shows_next_recrawl(client, admin_db):
    add(client, "http://a.com", recrawl_hours="2")
    conn = conn_of(admin_db)
    conn.execute("UPDATE seeds SET added_at = '2026-11-01T00:00:00Z'")
    conn.commit()
    body = client.get("/seeds").get_data(as_text=True)
    assert "Next recrawl" in body
    assert "2026-11-01T02:00:00Z" in body
