import re
from spiderlib import db

def conn_of(admin_db):
    return db.connect(admin_db)

def token(client, path="/urls"):
    response = client.get(path, follow_redirects=True)
    match = re.search(r'name="csrf" value="([^"]+)"', response.get_data(as_text=True))
    if match:
        return match.group(1)
    return None

def add(admin_db, url, status="done", **cols):
    conn = conn_of(admin_db)
    host = re.search(r'https?://([^/]+)', url).group(1)
    data = {"url": url, "host": host, "status": status, "added_at": db.now(), **cols}
    cur = conn.execute(
        "INSERT INTO urls (%s) VALUES (%s)" % (", ".join(data), ", ".join("?" * len(data))),
        list(data.values()))
    conn.commit()
    return cur.lastrowid

def test_requires_login(admin_client):
    response = admin_client.get("/urls")
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]

    response = admin_client.get("/urls/1")
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]

def test_empty_list(client):
    response = client.get("/urls")
    assert response.status_code == 200
    assert "No URLs match" in response.get_data(as_text=True)

def test_list_shows_rows_and_counts(client, admin_db):
    add(admin_db, "http://a.com/1")
    add(admin_db, "http://a.com/2")
    add(admin_db, "http://a.com/3", status="error")

    response = client.get("/urls")
    assert response.status_code == 200
    assert "http://a.com/1" in response.get_data(as_text=True)
    assert "http://a.com/2" in response.get_data(as_text=True)
    assert "http://a.com/3" in response.get_data(as_text=True)
    assert "done (2)" in response.get_data(as_text=True)
    assert "error (1)" in response.get_data(as_text=True)
    assert "3 URL(s)" in response.get_data(as_text=True)

def test_filter_by_status_and_search(client, admin_db):
    add(admin_db, "http://a.com/cats", title="Cats")
    add(admin_db, "http://a.com/dogs", title="Dogs")
    add(admin_db, "http://b.com/x", status="error")

    response = client.get("/urls?status=error")
    assert response.status_code == 200
    assert "http://b.com/x" in response.get_data(as_text=True)
    assert "http://a.com/cats" not in response.get_data(as_text=True)

    response = client.get("/urls?q=cats")
    assert response.status_code == 200
    assert "http://a.com/cats" in response.get_data(as_text=True)
    assert "http://a.com/dogs" not in response.get_data(as_text=True)

    response = client.get("/urls?host=b.com")
    assert response.status_code == 200
    assert "http://b.com/x" in response.get_data(as_text=True)
    assert "http://a.com/cats" not in response.get_data(as_text=True)

    response = client.get("/urls?status=bogus")
    assert response.status_code == 200
    assert "http://a.com/cats" in response.get_data(as_text=True)
    assert "http://a.com/dogs" in response.get_data(as_text=True)
    assert "http://b.com/x" in response.get_data(as_text=True)

def test_pagination_links(client, admin_db):
    for i in range(30):
        add(admin_db, f"http://a.com/p{i}")

    response = client.get("/urls?per_page=25")
    assert response.status_code == 200
    assert "Page 1 of 2" in response.get_data(as_text=True)
    assert "Next" in response.get_data(as_text=True)
    assert "Prev" not in response.get_data(as_text=True)

    response = client.get("/urls?per_page=25&page=2")
    assert response.status_code == 200
    assert "Page 2 of 2" in response.get_data(as_text=True)
    assert "Prev" in response.get_data(as_text=True)

    response = client.get("/urls?per_page=25&status=done")
    assert response.status_code == 200
    assert "status=done" in response.get_data(as_text=True)
    assert "page=2" in response.get_data(as_text=True)

def test_detail_page(client, admin_db):
    id1 = add(admin_db, "http://a.com/", title="Home")
    id2 = add(admin_db, "http://a.com/b")
    conn = conn_of(admin_db)
    conn.execute("INSERT INTO links (from_id, to_url) VALUES (?, ?)", (id1, "http://a.com/b"))
    conn.commit()

    response = client.get(f"/urls/{id1}")
    assert response.status_code == 200
    assert "Home" in response.get_data(as_text=True)
    assert "http://a.com/" in response.get_data(as_text=True)
    assert "Links on this page (1)" in response.get_data(as_text=True)
    assert f'href="/urls/{id2}"' in response.get_data(as_text=True)

    response = client.get(f"/urls/{id2}")
    assert response.status_code == 200
    assert "Linked from (1)" in response.get_data(as_text=True)

    response = client.get("/urls/9999")
    assert response.status_code == 404

def test_bulk_hide_and_flash(client, admin_db):
    id1 = add(admin_db, "http://a.com/1")
    id2 = add(admin_db, "http://a.com/2")

    response = client.post("/urls/action", data={
        "csrf": token(client),
        "action": "hide",
        "ids": [id1, id2],
        "next": "/urls"
    }, follow_redirects=True)
    assert response.status_code == 200
    assert "hide: 2 URL(s)." in response.get_data(as_text=True)

    conn = conn_of(admin_db)
    rows = conn.execute("SELECT hidden FROM urls WHERE id IN (?, ?)", (id1, id2)).fetchall()
    assert all(row[0] == 1 for row in rows)

def test_bulk_tag(client, admin_db):
    id1 = add(admin_db, "http://a.com/1")

    response = client.post("/urls/action", data={
        "csrf": token(client),
        "action": "tag_add",
        "value": "news",
        "ids": [id1],
        "next": "/urls"
    }, follow_redirects=True)
    assert response.status_code == 200

    conn = conn_of(admin_db)
    row = conn.execute("SELECT tags FROM urls WHERE id = ?", (id1,)).fetchone()
    assert row[0] == "news"

    response = client.post("/urls/action", data={
        "csrf": token(client),
        "action": "tag_add",
        "value": "bad tag",
        "ids": [id1],
        "next": "/urls"
    }, follow_redirects=True)
    assert response.status_code == 200
    assert "invalid tag" in response.get_data(as_text=True)

def test_bulk_delete_requires_confirm(client, admin_db):
    id1 = add(admin_db, "http://a.com/1")

    response = client.post("/urls/action", data={
        "csrf": token(client),
        "action": "delete",
        "ids": [id1],
        "next": "/urls"
    }, follow_redirects=True)
    assert response.status_code == 200
    assert "Tick confirm to delete." in response.get_data(as_text=True)

    conn = conn_of(admin_db)
    row = conn.execute("SELECT * FROM urls WHERE id = ?", (id1,)).fetchone()
    assert row is not None

    response = client.post("/urls/action", data={
        "csrf": token(client),
        "action": "delete",
        "ids": [id1],
        "confirm": "yes",
        "next": "/urls"
    }, follow_redirects=True)
    assert response.status_code == 200
    assert "delete: 1 URL(s)." in response.get_data(as_text=True)

    conn = conn_of(admin_db)
    row = conn.execute("SELECT * FROM urls WHERE id = ?", (id1,)).fetchone()
    assert row is None

def test_next_is_restricted(client, admin_db):
    id1 = add(admin_db, "http://a.com/1")

    response = client.post("/urls/action", data={
        "csrf": token(client),
        "action": "hide",
        "ids": [id1],
        "next": "http://evil.com/"
    })
    assert response.status_code == 302
    assert response.headers["Location"] == "/urls"

    response = client.post("/urls/action", data={
        "csrf": token(client),
        "action": "hide",
        "ids": [id1],
        "next": "/urls?status=done"
    })
    assert response.status_code == 302
    assert response.headers["Location"] == "/urls?status=done"

def test_single_action_and_delete(client, admin_db):
    id1 = add(admin_db, "http://a.com/1")

    response = client.post(f"/urls/{id1}/action", data={
        "csrf": token(client, f"/urls/{id1}"),
        "action": "approve"
    })
    assert response.status_code == 302
    assert f"/urls/{id1}" in response.headers["Location"]

    conn = conn_of(admin_db)
    row = conn.execute("SELECT approved FROM urls WHERE id = ?", (id1,)).fetchone()
    assert row[0] == 1

    response = client.post(f"/urls/{id1}/action", data={
        "csrf": token(client, f"/urls/{id1}"),
        "action": "delete",
        "confirm": "yes"
    })
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/urls")

    conn = conn_of(admin_db)
    row = conn.execute("SELECT * FROM urls WHERE id = ?", (id1,)).fetchone()
    assert row is None

    response = client.post("/urls/9999/action", data={
        "csrf": token(client, "/urls"),
        "action": "approve"
    })
    assert response.status_code == 404

def test_requeue_from_detail(client, admin_db):
    id1 = add(admin_db, "http://a.com/1", status="error", error="boom")

    response = client.post(f"/urls/{id1}/action", data={
        "csrf": token(client, f"/urls/{id1}"),
        "action": "requeue"
    }, follow_redirects=True)
    assert response.status_code == 200

    conn = conn_of(admin_db)
    row = conn.execute("SELECT status, error FROM urls WHERE id = ?", (id1,)).fetchone()
    assert row[0] == "queued"
    assert row[1] is None

def test_csrf_required(client, admin_db):
    response = client.post("/urls/action", data={
        "action": "hide",
        "ids": [1],
        "next": "/urls"
    })
    assert response.status_code == 400

    response = client.post("/urls/1/action", data={
        "action": "approve"
    })
    assert response.status_code == 400

def test_nav_has_urls_link(client):
    response = client.get("/")
    assert response.status_code == 200
    assert 'href="/urls"' in response.get_data(as_text=True)


def test_action_dropdowns_post_real_action_names(client, admin_db):
    uid = add(admin_db, "http://a.com/1")
    for path in ("/urls", "/urls/%d" % uid):
        body = client.get(path).get_data(as_text=True)
        for name in ("requeue", "hide", "unhide", "approve", "unapprove", "delete", "tag_add", "tag_remove"):
            assert '<option value="%s">' % name in body, (path, name)
