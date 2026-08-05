import streamlit.components.v1 as components


def sync_auth_to_local_storage(username: str):
    """Saves authenticated user session to browser localStorage and updates URL query param."""
    if not username:
        return
    clean_user = username.replace("'", "\\'").strip()
    js_code = f"""
    <script>
        try {{
            window.localStorage.setItem('analytics_session_user', '{clean_user}');
            const url = new URL(window.parent.location.href);
            if (url.searchParams.get('session_user') !== '{clean_user}') {{
                url.searchParams.set('session_user', '{clean_user}');
                window.parent.history.replaceState({{}}, '', url.toString());
            }}
        }} catch(e) {{
            console.error('LocalStorage sync error:', e);
        }}
    </script>
    """
    components.html(js_code, height=0, width=0)


def restore_auth_from_local_storage():
    """Reads browser localStorage on startup and syncs URL query params if missing."""
    js_code = """
    <script>
        try {
            const savedUser = window.localStorage.getItem('analytics_session_user');
            if (savedUser && savedUser !== 'null' && savedUser !== 'undefined' && savedUser.trim() !== '') {
                const parentUrl = new URL(window.parent.location.href);
                if (parentUrl.searchParams.get('session_user') !== savedUser) {
                    parentUrl.searchParams.set('session_user', savedUser);
                    window.parent.location.href = parentUrl.toString();
                }
            }
        } catch(e) {
            console.error('LocalStorage restore error:', e);
        }
    </script>
    """
    components.html(js_code, height=0, width=0)


def clear_local_storage_auth():
    """Clears session_user from browser localStorage and URL query params on Sign Out."""
    js_code = """
    <script>
        try {
            window.localStorage.removeItem('analytics_session_user');
            const parentUrl = new URL(window.parent.location.href);
            if (parentUrl.searchParams.has('session_user')) {
                parentUrl.searchParams.delete('session_user');
                window.parent.history.replaceState({}, '', parentUrl.toString());
            }
        } catch(e) {
            console.error('LocalStorage clear error:', e);
        }
    </script>
    """
    components.html(js_code, height=0, width=0)
