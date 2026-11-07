import re
from spiderlib import db

def conn_of(admin_db):
    return db.connect(admin_db)

def token(client, path="/domains"):
    response = client.get(path, follow_redirects=True)
    match = re.search(r'name="csrf" value="([^"]+)"', response.get_data(as_text=True))
    if match:
        return match.group(1)
    return None

def add(admin_db, url, host, status="done", **cols):
    conn = conn_of(admin_db)
    data = {"url": url, "host": host, "status": status, "added_at": db.now(), **cols}
    cur = conn.execute(
        "INSERT INTO urls (%s) VALUES (%s)" % (", ".join(data), ", ".join("?" * len(data))),
        list(data.values()))
    conn.commit()
    return cur.lastrowid

def dom(admin_db, host):
    conn = conn_of(admin_db)
    result = conn.execute("SELECT * FROM domains WHERE host = ?", (host,)).fetchone()
    return dict(result) if result else None

def test_requires_login(admin_client):
    response = admin_client.get("/domains")
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]

    response = admin_client.get("/domains/a.com")
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]

def test_empty_list(client):
    response = client.get("/domains")
    assert response.status_code == 200
    assert "No domains yet" in response.get_data(as_text=True)
    assert "also blocks its subdomains" in response.get_data(as_text=True)

def test_list_shows_hosts_and_counts(client, admin_db):
    add(admin_db, "http://a.com/page1", "a.com", "done")
    add(admin_db, "http://a.com/page2", "a.com", "error")
    add(admin_db, "http://b.org/page1", "b.org", "done")

    response = client.get("/domains")
    assert response.status_code == 200
    assert "a.com" in response.get_data(as_text=True)
    assert "b.org" in response.get_data(as_text=True)
    assert 'href="/domains/a.com"' in response.get_data(as_text=True)
    assert "2 domain(s)" in response.get_data(as_text=True)

def test_list_filters(client, admin_db):
    add(admin_db, "http://a.com/page1", "a.com", "done")
    add(admin_db, "http://b.org/page1", "b.org", "done")
    client.post("/domains/b.org/block", data={"csrf": token(client, "/domains/b.org")})

    response = client.get("/domains?blocked=yes")
    assert response.status_code == 200
    assert 'href="/domains/b.org"' in response.get_data(as_text=True)
    assert 'href="/domains/a.com"' not in response.get_data(as_text=True)

    response = client.get("/domains?q=a.c")
    assert response.status_code == 200
    assert "a.com" in response.get_data(as_text=True)
    assert "b.org" not in response.get_data(as_text=True)

    response = client.get("/domains?sort=evil")
    assert response.status_code == 200

def test_block_new_host(client, admin_db):
    csrf_token = token(client)
    response = client.post("/domains/block", data={"csrf": csrf_token, "host": "Spam.Example"}, follow_redirects=True)
    assert response.status_code == 200
    assert "Domain blocked." in response.get_data(as_text=True)
    assert "spam.example" in response.get_data(as_text=True)
    assert dom(admin_db, "spam.example")["blocked"] == 1

    response = client.post("/domains/block", data={"csrf": csrf_token, "host": "not a host"}, follow_redirects=True)
    assert response.status_code == 200
    assert "Not a valid host name." in response.get_data(as_text=True)

def test_detail_page(client, admin_db):
    add(admin_db, "http://a.com/page1", "a.com", "done", title="Page Title")

    response = client.get("/domains/a.com")
    assert response.status_code == 200
    assert "a.com" in response.get_data(as_text=True)
    assert "Block this domain" in response.get_data(as_text=True)
    assert "Save delay" in response.get_data(as_text=True)
    assert "Save notes" in response.get_data(as_text=True)
    assert "Refetch robots.txt" in response.get_data(as_text=True)
    assert "not fetched" in response.get_data(as_text=True)
    assert "http://a.com/page1" in response.get_data(as_text=True)

    response = client.get("/domains/unknown.org")
    assert response.status_code == 404

    response = client.get("/domains/A.COM")
    assert response.status_code == 200

def test_block_unblock_from_detail(client, admin_db):
    add(admin_db, "http://a.com/page1", "a.com", "done")

    csrf_token = token(client, "/domains/a.com")
    response = client.post("/domains/a.com/block", data={"csrf": csrf_token})
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/domains/a.com")
    assert dom(admin_db, "a.com")["blocked"] == 1

    response = client.get("/domains/a.com")
    assert response.status_code == 200
    assert "Unblock" in response.get_data(as_text=True)

    response = client.post("/domains/a.com/unblock", data={"csrf": csrf_token}, follow_redirects=True)
    assert dom(admin_db, "a.com")["blocked"] == 0

    response = client.post("/domains/bad%20host/block", data={"csrf": csrf_token}, follow_redirects=True)
    assert response.status_code == 404

def test_delay_and_notes(client, admin_db):
    add(admin_db, "http://a.com/page1", "a.com", "done")

    csrf_token = token(client, "/domains/a.com")
    response = client.post("/domains/a.com/delay", data={"csrf": csrf_token, "delay": "3"}, follow_redirects=True)
    assert response.status_code == 200
    assert "Delay saved." in response.get_data(as_text=True)
    assert dom(admin_db, "a.com")["delay_override"] == 3.0

    response = client.post("/domains/a.com/delay", data={"csrf": csrf_token, "delay": "abc"}, follow_redirects=True)
    assert response.status_code == 200
    assert "must be a number" in response.get_data(as_text=True)

    response = client.post("/domains/a.com/notes", data={"csrf": csrf_token, "notes": "be gentle"}, follow_redirects=True)
    assert response.status_code == 200
    assert "Notes saved." in response.get_data(as_text=True)
    assert "be gentle" in response.get_data(as_text=True)

def test_robots_refetch_uses_configured_fetcher(client, admin_app, admin_db):
    add(admin_db, "http://a.com/page1", "a.com", "done")

    def fetcher(url, ua, timeout):
        return (200, "User-agent: *\nDisallow: /private/")

    admin_app.config["ROBOTS_FETCHER"] = fetcher

    csrf_token = token(client, "/domains/a.com")
    response = client.post("/domains/a.com/robots", data={"csrf": csrf_token}, follow_redirects=True)
    assert response.status_code == 200
    assert "robots.txt refetched (status 200)" in response.get_data(as_text=True)
    assert "Disallow: /private/" in response.get_data(as_text=True)

def test_csrf_required(client, admin_db):
    response = client.post("/domains/block", follow_redirects=True)
    assert response.status_code == 400

    response = client.post("/domains/a.com/block", follow_redirects=True)
    assert response.status_code == 400

def test_nav_has_domains_link(client):
    response = client.get("/")
    assert response.status_code == 200
    assert 'href="/domains"' in response.get_data(as_text=True)
