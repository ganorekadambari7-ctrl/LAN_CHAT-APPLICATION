"""
LAN Chat Server v5 Upgraded
New: Admin Login Panel, Admin DM to clients, Encryption at server,
     Group member visibility
"""

import socket, threading, json, hashlib, time, os
from datetime import datetime
from collections import defaultdict
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import base64

try:
    from crypto_utils import encrypt, decrypt, derive_key
    HAS_CRYPTO = True
except ImportError:
    HAS_CRYPTO = False

DISCOVERY_PORT = 9091
LOG_FILE = 'chat_server_log.txt'
ADMIN_USERNAME = 'admin'
ADMIN_PASSWORD = 'admin123'   # default — changeable at login


def hash_pw(p): return hashlib.sha256(p.encode()).hexdigest()


# ══════════════════════════════════════════════════════════════════════
#  CHAT SERVER CORE
# ══════════════════════════════════════════════════════════════════════
class ChatServer:
    def __init__(self):
        self.host = '0.0.0.0'
        self.port = 9090
        self.clients = {}       # sock -> {username, color, msg_count, blocked}
        self.accounts = {}      # username -> hashed_password
        self.lock = threading.Lock()
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

        self.total_messages = 0
        self.hourly_counts = defaultdict(int)
        self.start_time = time.time()
        self.all_messages = []

        self.pinned = []
        self.messages = {}
        self._msg_counter = 0
        self.read_by = defaultdict(set)

        self.spam_tracker = defaultdict(list)
        self.MUTED = {}

        self.groups = {}
        self._group_counter = 0

        self.room_password_hash = None
        self.on_event = None
        self.enc_key = None   # set by admin panel after login

        self._log(f'=== Server v5u started {datetime.now().strftime("%Y-%m-%d %H:%M:%S")} ===')

    def _log(self, line):
        ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        entry = f'[{ts}] {line}'
        try:
            with open(LOG_FILE, 'a', encoding='utf-8') as f:
                f.write(entry + '\n')
        except Exception:
            pass
        if self.on_event:
            self.on_event('log', entry)

    def _new_msg_id(self):
        self._msg_counter += 1
        return f'msg_{self._msg_counter}'

    def _all_users(self):
        with self.lock:
            return [
                {'username': v['username'],
                 'avatar_color': v.get('avatar_color', '#7c6af7'),
                 'msg_count': v.get('msg_count', 0),
                 'blocked': v.get('blocked', False)}
                for v in self.clients.values()
            ]

    def broadcast(self, message, exclude=None):
        data = (json.dumps(message) + '\n').encode('utf-8')
        with self.lock:
            for sock in list(self.clients.keys()):
                if sock == exclude:
                    continue
                try:
                    sock.sendall(data)
                except Exception:
                    pass

    def send_to(self, sock, message):
        try:
            sock.sendall((json.dumps(message) + '\n').encode('utf-8'))
        except Exception:
            pass

    def send_to_username(self, username, message):
        sock = self._find_sock(username)
        if sock:
            self.send_to(sock, message)
            return True
        return False

    def _find_sock(self, username):
        with self.lock:
            for s, v in self.clients.items():
                if v['username'] == username:
                    return s
        return None

    def _stats_payload(self):
        uptime_s = int(time.time() - self.start_time)
        h, rem = divmod(uptime_s, 3600)
        m, s = divmod(rem, 60)
        with self.lock:
            online = len(self.clients)
        peak_hour = max(self.hourly_counts, key=self.hourly_counts.get) if self.hourly_counts else 0
        return {
            'total_messages': self.total_messages,
            'online_now': online,
            'uptime': f'{h:02d}:{m:02d}:{s:02d}',
            'peak_hour': peak_hour,
            'hourly': dict(self.hourly_counts),
        }

    def _check_spam(self, username):
        now = time.time()
        if username in self.MUTED:
            if now < self.MUTED[username]:
                return True
            else:
                del self.MUTED[username]
        times = [t for t in self.spam_tracker[username] if now - t < 5]
        times.append(now)
        self.spam_tracker[username] = times
        if len(times) > 5:
            self.MUTED[username] = now + 30
            return True
        return False

    # ── Admin actions ──────────────────────────────────────────────────
    def admin_broadcast(self, text, encrypted=False):
        ts = datetime.now().strftime('%H:%M')
        send_text = text
        if encrypted and self.enc_key and HAS_CRYPTO:
            send_text = encrypt(text, self.enc_key)
        payload = {
            'type': 'message', 'id': self._new_msg_id(),
            'from': '📢 ADMIN', 'text': send_text,
            'time': ts, 'encrypted': encrypted, 'is_admin': True,
        }
        self.broadcast(payload)
        self.all_messages.append(payload)
        self._log(f'ADMIN BROADCAST: {text}')
        if self.on_event:
            self.on_event('message', {'from': '📢 ADMIN', 'text': text, 'time': ts})

    def admin_dm(self, target_username, text, encrypted=False):
        """Admin sends private DM to a specific user."""
        ts = datetime.now().strftime('%H:%M')
        send_text = text
        if encrypted and self.enc_key and HAS_CRYPTO:
            send_text = encrypt(text, self.enc_key)
        payload = {
            'type': 'private', 'id': self._new_msg_id(),
            'from': '📢 ADMIN', 'to': target_username,
            'text': send_text, 'time': ts,
            'encrypted': encrypted, 'is_admin': True,
        }
        ok = self.send_to_username(target_username, payload)
        self._log(f'ADMIN DM → {target_username}: {text}')
        if self.on_event:
            self.on_event('admin_dm', {
                'to': target_username, 'text': text, 'time': ts, 'ok': ok
            })
        return ok

    def admin_send_file(self, filepath):
        try:
            filename = os.path.basename(filepath)
            with open(filepath, 'rb') as f:
                data = f.read()
            if len(data) > 10 * 1024 * 1024:
                return False, 'File too large (max 10MB)'
            ts = datetime.now().strftime('%H:%M')
            payload = {
                'type': 'file', 'from': '📢 ADMIN',
                'filename': filename, 'filesize': len(data),
                'filedata': base64.b64encode(data).decode(), 'time': ts,
            }
            self.broadcast(payload)
            self._log(f'ADMIN FILE: {filename}')
            return True, f'"{filename}" sent to all users'
        except Exception as e:
            return False, str(e)

    def admin_block(self, username):
        with self.lock:
            for sock, v in self.clients.items():
                if v['username'] == username:
                    v['blocked'] = True
                    break
        self.send_to_username(username, {
            'type': 'system',
            'text': '🚫 You have been blocked by the admin.'
        })
        self.broadcast({
            'type': 'system',
            'text': f'🚫 {username} has been blocked by admin.',
            'users': self._all_users(),
        })
        self._log(f'ADMIN BLOCKED: {username}')

    def admin_unblock(self, username):
        with self.lock:
            for sock, v in self.clients.items():
                if v['username'] == username:
                    v['blocked'] = False
                    break
        self.send_to_username(username, {
            'type': 'system',
            'text': '✅ You have been unblocked by the admin.'
        })
        self.broadcast({
            'type': 'system',
            'text': f'✅ {username} has been unblocked by admin.',
            'users': self._all_users(),
        })
        self._log(f'ADMIN UNBLOCKED: {username}')

    def admin_kick(self, username):
        sock = self._find_sock(username)
        if sock:
            self.send_to(sock, {
                'type': 'error', 'text': '🚫 You have been kicked by the admin.'
            })
            try:
                sock.close()
            except Exception:
                pass
        self._log(f'ADMIN KICKED: {username}')

    # ── Groups ─────────────────────────────────────────────────────────
    def create_group(self, creator, group_name, members):
        self._group_counter += 1
        group_id = f'grp_{self._group_counter}'
        member_set = set(members) | {creator}
        self.groups[group_id] = {
            'id': group_id, 'name': group_name,
            'creator': creator, 'members': member_set,
        }
        for member in member_set:
            self.send_to_username(member, {
                'type': 'group_created',
                'group_id': group_id,
                'group_name': group_name,
                'creator': creator,
                'members': list(member_set),
            })
        self._log(f'GROUP: {group_name} by {creator}, members: {member_set}')
        if self.on_event:
            self.on_event('group_created', {
                'name': group_name, 'creator': creator,
                'members': list(member_set)
            })
        return group_id

    # ── Client Handler ─────────────────────────────────────────────────
    def handle_client(self, client_sock, addr):
        buffer = ''
        username = None
        try:
            while True:
                chunk = client_sock.recv(65536).decode('utf-8', errors='replace')
                if not chunk:
                    break
                buffer += chunk
                while '\n' in buffer:
                    line, buffer = buffer.split('\n', 1)
                    if not line.strip():
                        continue
                    try:
                        msg = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    kind = msg.get('type')

                    if kind == 'join':
                        if self.room_password_hash:
                            if hash_pw(msg.get('room_password', '')) != self.room_password_hash:
                                self.send_to(client_sock, {'type': 'error', 'text': 'Wrong room password!'})
                                return

                        uname = msg.get('username', 'Anon')[:20]
                        color = msg.get('avatar_color', '#7c6af7')
                        user_password = msg.get('user_password', '')

                        with self.lock:
                            taken = any(v['username'] == uname for v in self.clients.values())
                        if taken:
                            self.send_to(client_sock, {'type': 'error', 'text': f'Username "{uname}" is taken.'})
                            return

                        if uname in self.accounts:
                            if self.accounts[uname] != hash_pw(user_password):
                                self.send_to(client_sock, {'type': 'error', 'text': f'Wrong password for "{uname}".'})
                                return
                        elif user_password:
                            self.accounts[uname] = hash_pw(user_password)

                        username = uname
                        with self.lock:
                            self.clients[client_sock] = {
                                'username': username, 'avatar_color': color,
                                'joined_at': datetime.now().isoformat(),
                                'msg_count': 0, 'blocked': False,
                            }

                        self._log(f'JOIN {username} from {addr}')
                        self.send_to(client_sock, {
                            'type': 'welcome',
                            'text': f'Welcome, {username}!',
                            'users': self._all_users(),
                            'pinned': self.pinned,
                            'stats': self._stats_payload(),
                            'recent_messages': list(self.messages.values())[-50:],
                            'groups': [
                                {'id': g['id'], 'name': g['name'],
                                 'creator': g['creator'], 'members': list(g['members'])}
                                for g in self.groups.values()
                                if username in g['members']
                            ],
                        })
                        self.broadcast({
                            'type': 'system',
                            'text': f'{username} has joined the chat.',
                            'users': self._all_users(),
                        }, exclude=client_sock)
                        if self.on_event:
                            self.on_event('user_join', {'username': username, 'addr': str(addr)})

                    elif kind == 'message':
                        if not username:
                            continue
                        with self.lock:
                            blocked = self.clients.get(client_sock, {}).get('blocked', False)
                        if blocked:
                            self.send_to(client_sock, {'type': 'system', 'text': '🚫 You are blocked.'})
                            continue
                        if self._check_spam(username):
                            remaining = int(self.MUTED.get(username, time.time()) - time.time())
                            self.send_to(client_sock, {
                                'type': 'system',
                                'text': f'⚠️ Sending too fast! Muted for {remaining}s.'
                            })
                            continue

                        text = msg.get('text', '').strip()
                        if not text:
                            continue

                        ts = datetime.now()
                        msg_id = self._new_msg_id()
                        self.total_messages += 1
                        self.hourly_counts[ts.hour] += 1
                        with self.lock:
                            if client_sock in self.clients:
                                self.clients[client_sock]['msg_count'] += 1

                        reply_to = msg.get('reply_to')
                        reply_preview = None
                        if reply_to and reply_to in self.messages:
                            orig = self.messages[reply_to]
                            reply_preview = {'from': orig['from'], 'text': orig['text'][:60]}

                        entry = {
                            'id': msg_id, 'from': username, 'text': text,
                            'time': ts.strftime('%H:%M'),
                            'encrypted': msg.get('encrypted', False),
                            'reply_to': reply_to, 'reply_preview': reply_preview,
                            'reactions': {}, 'deleted': False, 'edited': False,
                        }
                        self.messages[msg_id] = entry
                        self.all_messages.append(entry)

                        # Decrypt for admin monitoring if key set
                        display_text = text
                        if entry['encrypted'] and self.enc_key and HAS_CRYPTO:
                            try:
                                display_text = decrypt(text, self.enc_key)
                            except Exception:
                                display_text = '[encrypted]'

                        self._log(f'MSG [{username}]: {display_text[:80]}')
                        payload = dict(entry); payload['type'] = 'message'
                        self.broadcast(payload)
                        if self.on_event:
                            self.on_event('message', {**entry, 'display_text': display_text})

                    elif kind == 'private':
                        if not username:
                            continue
                        with self.lock:
                            blocked = self.clients.get(client_sock, {}).get('blocked', False)
                        if blocked:
                            self.send_to(client_sock, {'type': 'system', 'text': '🚫 You are blocked.'})
                            continue

                        target = msg.get('to')
                        text = msg.get('text', '').strip()
                        if not text or not target:
                            continue

                        ts = datetime.now().strftime('%H:%M')
                        msg_id = self._new_msg_id()
                        reply_to = msg.get('reply_to')
                        reply_preview = None
                        if reply_to and reply_to in self.messages:
                            orig = self.messages[reply_to]
                            reply_preview = {'from': orig['from'], 'text': orig['text'][:60]}

                        payload = {
                            'type': 'private', 'id': msg_id,
                            'from': username, 'to': target,
                            'text': text, 'time': ts,
                            'encrypted': msg.get('encrypted', False),
                            'reply_to': reply_to, 'reply_preview': reply_preview,
                        }
                        tsock = self._find_sock(target)
                        if tsock:
                            self.send_to(tsock, payload)
                            self.send_to(client_sock, payload)
                        else:
                            self.send_to(client_sock, {'type': 'system', 'text': f'User "{target}" not found.'})

                        # Decrypt for admin monitoring
                        display_text = text
                        if msg.get('encrypted') and self.enc_key and HAS_CRYPTO:
                            try:
                                display_text = decrypt(text, self.enc_key)
                            except Exception:
                                display_text = '[encrypted]'
                        self._log(f'DM [{username}→{target}]: {display_text[:60]}')
                        if self.on_event:
                            self.on_event('private_msg', {
                                'from': username, 'to': target,
                                'text': display_text, 'time': ts
                            })

                    elif kind == 'group_message':
                        if not username:
                            continue
                        with self.lock:
                            blocked = self.clients.get(client_sock, {}).get('blocked', False)
                        if blocked:
                            continue

                        group_id = msg.get('group_id')
                        text = msg.get('text', '').strip()
                        if not text or group_id not in self.groups:
                            continue
                        group = self.groups[group_id]
                        if username not in group['members']:
                            continue

                        ts = datetime.now().strftime('%H:%M')
                        msg_id = self._new_msg_id()
                        payload = {
                            'type': 'group_message', 'id': msg_id,
                            'group_id': group_id, 'group_name': group['name'],
                            'from': username, 'text': text,
                            'time': ts, 'encrypted': msg.get('encrypted', False),
                        }
                        for member in group['members']:
                            self.send_to_username(member, payload)
                        self._log(f'GROUP [{group["name"]}] {username}: {text[:60]}')

                    elif kind == 'create_group':
                        if not username:
                            continue
                        group_name = msg.get('group_name', 'Group')
                        members = msg.get('members', [])
                        if members:
                            self.create_group(username, group_name, members)

                    elif kind == 'typing':
                        if not username:
                            continue
                        self.broadcast({
                            'type': 'typing', 'from': username,
                            'is_typing': msg.get('is_typing', False),
                        }, exclude=client_sock)

                    elif kind == 'file':
                        if not username:
                            continue
                        with self.lock:
                            blocked = self.clients.get(client_sock, {}).get('blocked', False)
                        if blocked:
                            self.send_to(client_sock, {'type': 'system', 'text': '🚫 You are blocked.'})
                            continue
                        ts = datetime.now().strftime('%H:%M')
                        target = msg.get('to')
                        payload = {
                            'type': 'file', 'from': username,
                            'filename': msg.get('filename', 'file'),
                            'filesize': msg.get('filesize', 0),
                            'filedata': msg.get('filedata', ''),
                            'time': ts,
                        }
                        if target:
                            payload['to'] = target
                            tsock = self._find_sock(target)
                            if tsock:
                                self.send_to(tsock, payload)
                                self.send_to(client_sock, payload)
                        else:
                            self.broadcast(payload)
                        self._log(f'FILE [{username}]: {msg.get("filename")}')

                    elif kind == 'edit':
                        if not username:
                            continue
                        msg_id = msg.get('msg_id')
                        new_text = msg.get('text', '').strip()
                        if msg_id in self.messages:
                            entry = self.messages[msg_id]
                            if entry['from'] == username and not entry['deleted']:
                                entry['text'] = new_text; entry['edited'] = True
                                self.broadcast({'type': 'edit', 'msg_id': msg_id,
                                                'text': new_text, 'edited': True})

                    elif kind == 'delete':
                        if not username:
                            continue
                        msg_id = msg.get('msg_id')
                        if msg_id in self.messages:
                            entry = self.messages[msg_id]
                            if entry['from'] == username:
                                entry['deleted'] = True
                                entry['text'] = '[Message deleted]'
                                self.broadcast({'type': 'delete', 'msg_id': msg_id})

                    elif kind == 'react':
                        if not username:
                            continue
                        msg_id = msg.get('msg_id'); emoji = msg.get('emoji', '')
                        if msg_id in self.messages and emoji:
                            entry = self.messages[msg_id]
                            if emoji not in entry['reactions']:
                                entry['reactions'][emoji] = []
                            if username in entry['reactions'][emoji]:
                                entry['reactions'][emoji].remove(username)
                            else:
                                entry['reactions'][emoji].append(username)
                            entry['reactions'] = {e: u for e, u in entry['reactions'].items() if u}
                            self.broadcast({'type': 'react_update', 'msg_id': msg_id,
                                            'reactions': entry['reactions']})

                    elif kind == 'read':
                        if not username:
                            continue
                        msg_id = msg.get('msg_id')
                        if msg_id:
                            self.read_by[msg_id].add(username)
                            if msg_id in self.messages:
                                sender = self.messages[msg_id]['from']
                                ssock = self._find_sock(sender)
                                if ssock:
                                    self.send_to(ssock, {
                                        'type': 'read_receipt', 'msg_id': msg_id,
                                        'by': username,
                                        'read_by': list(self.read_by[msg_id]),
                                    })

                    elif kind == 'pin':
                        if not username:
                            continue
                        text = msg.get('text', '').strip()
                        if text:
                            self.pinned = ([{
                                'text': text, 'by': username,
                                'time': datetime.now().strftime('%H:%M %d/%m'),
                            }] + self.pinned)[:10]
                            self.broadcast({'type': 'pin_update',
                                            'pinned': self.pinned, 'by': username})

                    elif kind == 'unpin':
                        idx = msg.get('index', -1)
                        if 0 <= idx < len(self.pinned):
                            self.pinned.pop(idx)
                            self.broadcast({'type': 'pin_update',
                                            'pinned': self.pinned, 'by': username})

                    elif kind == 'get_stats':
                        self.send_to(client_sock, {
                            'type': 'stats',
                            'data': self._stats_payload(),
                            'users': self._all_users(),
                        })

        except Exception as e:
            self._log(f'ERROR {addr}: {e}')
        finally:
            with self.lock:
                self.clients.pop(client_sock, None)
            client_sock.close()
            if username:
                self._log(f'LEAVE {username}')
                self.broadcast({
                    'type': 'system',
                    'text': f'{username} has left the chat.',
                    'users': self._all_users(),
                })
                if self.on_event:
                    self.on_event('user_leave', {'username': username})

    def _run_discovery(self, local_ip):
        udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        udp.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            udp.bind(('', DISCOVERY_PORT))
            udp.settimeout(1.0)
            while True:
                try:
                    data, addr = udp.recvfrom(256)
                    if data == b'LANCHAT_DISCOVER':
                        reply = json.dumps({
                            'service': 'lanchat', 'ip': local_ip,
                            'port': self.port, 'name': f'LAN Chat @ {local_ip}',
                        }).encode()
                        udp.sendto(reply, addr)
                except socket.timeout:
                    pass
        except Exception:
            pass
        finally:
            udp.close()

    def start(self):
        self.server_socket.bind((self.host, self.port))
        self.server_socket.listen(50)
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(('8.8.8.8', 80))
            local_ip = s.getsockname()[0]
            s.close()
        except Exception:
            local_ip = '127.0.0.1'
        self.local_ip = local_ip
        threading.Thread(target=self._run_discovery, args=(local_ip,), daemon=True).start()
        threading.Thread(target=self._accept_loop, daemon=True).start()
        return local_ip

    def _accept_loop(self):
        try:
            while True:
                sock, addr = self.server_socket.accept()
                threading.Thread(target=self.handle_client,
                                 args=(sock, addr), daemon=True).start()
        except Exception:
            pass


# ══════════════════════════════════════════════════════════════════════
#  COLORS & FONTS
# ══════════════════════════════════════════════════════════════════════
C = {
    'bg': '#0f1117', 'sidebar': '#090b12', 'panel': '#161924',
    'input_bg': '#1e2235', 'accent': '#7c6af7', 'accent2': '#5eead4',
    'text': '#e2e8f0', 'text_dim': '#8892a4', 'online': '#4ade80',
    'border': '#2e3250', 'hover': '#1e2235', 'danger': '#f87171',
    'warn': '#fbbf24', 'success': '#4ade80', 'dm_bg': '#1a1535',
}
FT  = ('Segoe UI', 10)
FB  = ('Segoe UI', 10, 'bold')
FS  = ('Segoe UI', 9)
FT2 = ('Segoe UI', 14, 'bold')
FM  = ('Consolas', 9)


# ══════════════════════════════════════════════════════════════════════
#  ADMIN LOGIN DIALOG
# ══════════════════════════════════════════════════════════════════════
class AdminLoginDialog(tk.Toplevel):
    def __init__(self, parent, prefill_room_pw=''):
        super().__init__(parent)
        self.result = None
        self._prefill_room_pw = prefill_room_pw
        self.title('Admin Login — LAN Chat v5')
        self.configure(bg=C['bg'])
        self.resizable(False, False)
        self.grab_set()
        self._build()
        self.protocol('WM_DELETE_WINDOW', self._cancel)
        self.after(100, self._center)

    def _center(self):
        self.update_idletasks()
        x = (self.winfo_screenwidth()  - self.winfo_width())  // 2
        y = (self.winfo_screenheight() - self.winfo_height()) // 2
        self.geometry(f'+{x}+{y}')

    def _build(self):
        tk.Label(self, text='🛡️ Admin Login', font=FT2,
                 bg=C['bg'], fg=C['accent']).pack(pady=(24, 4))
        tk.Label(self, text='Enter credentials to access the Admin Panel',
                 font=FS, bg=C['bg'], fg=C['text_dim']).pack(pady=(0, 16))

        frame = tk.Frame(self, bg=C['panel']); frame.pack(fill='x', padx=28, pady=4)

        def field(lbl, default='', show=None):
            tk.Label(frame, text=lbl, font=FS, bg=C['panel'],
                     fg=C['text_dim'], anchor='w').pack(fill='x', padx=16, pady=(8, 0))
            e = tk.Entry(frame, font=FT, bg=C['input_bg'], fg=C['text'],
                         insertbackground=C['accent'], relief='flat', bd=6, show=show)
            e.insert(0, default)
            e.pack(fill='x', padx=16, pady=(0, 4))
            return e

        self.user_e = field('Admin Username', ADMIN_USERNAME)
        self.pass_e = field('Admin Password', '', show='•')
        self.enc_e  = field('Encryption Passphrase (optional — to read encrypted messages)', '')
        self.room_pass_e = field('Room Password (optional — leave blank = open server)', self._prefill_room_pw, show='•')

        self.pass_e.focus_set()

        tk.Label(frame, text=f'Default: {ADMIN_USERNAME} / {ADMIN_PASSWORD}',
                 font=('Segoe UI', 8), bg=C['panel'],
                 fg=C['text_dim']).pack(anchor='w', padx=16, pady=(0, 10))

        bf = tk.Frame(self, bg=C['bg']); bf.pack(fill='x', padx=28, pady=14)
        tk.Button(bf, text='Cancel', font=FT, bg=C['panel'], fg=C['text_dim'],
                  relief='flat', bd=0, padx=14, pady=8, cursor='hand2',
                  command=self._cancel).pack(side='left')
        tk.Button(bf, text='Login →', font=FB, bg=C['accent'], fg='white',
                  relief='flat', bd=0, padx=20, pady=8, cursor='hand2',
                  command=self._login).pack(side='right')
        self.bind('<Return>', lambda e: self._login())

    def _login(self):
        uname = self.user_e.get().strip()
        passwd = self.pass_e.get().strip()
        passphrase = self.enc_e.get().strip()
        if uname != ADMIN_USERNAME or passwd != ADMIN_PASSWORD:
            messagebox.showerror('Login Failed',
                                 'Wrong username or password.\n'
                                 f'Default: {ADMIN_USERNAME} / {ADMIN_PASSWORD}',
                                 parent=self)
            return
        self.result = {'username': uname, 'passphrase': passphrase, 'room_password': self.room_pass_e.get().strip()}
        self.destroy()

    def _cancel(self):
        self.result = None
        self.destroy()


# ══════════════════════════════════════════════════════════════════════
#  ADMIN PANEL
# ══════════════════════════════════════════════════════════════════════
class AdminPanel(tk.Tk):
    def __init__(self, cmdline_room_pw='', cmdline_port=9090):
        super().__init__()
        self.withdraw()
        self.title('LAN Chat v5 — Admin Panel')
        self.geometry('1120x720')
        self.minsize(900, 600)
        self.configure(bg=C['bg'])
        self.server = ChatServer()
        self.server.port = cmdline_port
        self.server.on_event = self._on_server_event
        self._dm_target = None
        self._cmdline_room_pw = cmdline_room_pw
        self._build_login()
        self.protocol('WM_DELETE_WINDOW', self._on_close)

    # ── Login flow ─────────────────────────────────────────────────────
    def _build_login(self):
        dlg = AdminLoginDialog(self, prefill_room_pw=self._cmdline_room_pw)
        self.wait_window(dlg)
        if not dlg.result:
            self.destroy()
            return
        # Set encryption key if passphrase provided
        if dlg.result['passphrase'] and HAS_CRYPTO:
            self.server.enc_key = derive_key(dlg.result['passphrase'])
            self._enc_enabled = True
        else:
            self._enc_enabled = False

        # Set room password if provided
        room_pw = dlg.result.get('room_password', '')
        if room_pw:
            self.server.room_password_hash = hash_pw(room_pw)
            self._room_pw_set = True
        else:
            self.server.room_password_hash = None
            self._room_pw_set = False

        self._build_ui()
        local_ip = self.server.start()
        lock_status = '🔒 Room Locked' if self._room_pw_set else '🔓 Open Room'
        enc_status = '🔐 Encrypted' if self._enc_enabled else '🔓 No Encryption'
        self.ip_label.config(
            text=f'IP: {local_ip}:9090  |  🟢 Running  |  {lock_status}  |  {enc_status}')
        self._log_line(f'Admin logged in. Server started — {local_ip}:9090')
        self.deiconify()
        self._center_window()
        self._refresh_loop()

    def _center_window(self):
        self.update_idletasks()
        x = (self.winfo_screenwidth()  - self.winfo_width())  // 2
        y = (self.winfo_screenheight() - self.winfo_height()) // 2
        self.geometry(f'+{x}+{y}')

    # ── UI ─────────────────────────────────────────────────────────────
    def _build_ui(self):
        # Top bar
        topbar = tk.Frame(self, bg=C['panel'], height=50)
        topbar.pack(fill='x'); topbar.pack_propagate(False)
        tk.Label(topbar, text='🛡️ LAN Chat v5 — Admin Panel',
                 font=FT2, bg=C['panel'], fg=C['accent']).pack(side='left', padx=16, pady=10)
        self.ip_label = tk.Label(topbar, text='Starting...',
                                  font=FS, bg=C['panel'], fg=C['text_dim'])
        self.ip_label.pack(side='right', padx=16)

        # Main
        content = tk.Frame(self, bg=C['bg']); content.pack(fill='both', expand=True)

        # ── Left panel — Users + DM ──
        left = tk.Frame(content, bg=C['sidebar'], width=260)
        left.pack(side='left', fill='y'); left.pack_propagate(False)

        tk.Label(left, text='CONNECTED USERS', font=('Segoe UI', 8, 'bold'),
                 bg=C['sidebar'], fg=C['text_dim'], padx=14, pady=8, anchor='w').pack(fill='x')
        self.user_frame = tk.Frame(left, bg=C['sidebar'])
        self.user_frame.pack(fill='both', expand=True)
        self.user_count_label = tk.Label(left, text='0 users online',
                                          font=FS, bg=C['sidebar'], fg=C['text_dim'])
        self.user_count_label.pack(pady=2)

        # DM section
        sep = tk.Frame(left, bg=C['border'], height=1); sep.pack(fill='x', padx=8, pady=4)
        tk.Label(left, text='💬 DIRECT MESSAGE TO USER',
                 font=('Segoe UI', 8, 'bold'),
                 bg=C['sidebar'], fg=C['accent2'], padx=14, pady=6, anchor='w').pack(fill='x')

        self.dm_target_label = tk.Label(left, text='No user selected',
                                         font=FS, bg=C['sidebar'], fg=C['text_dim'],
                                         padx=14, anchor='w')
        self.dm_target_label.pack(fill='x')

        dm_input_frame = tk.Frame(left, bg=C['panel']); dm_input_frame.pack(fill='x', padx=8, pady=4)
        self.dm_var = tk.StringVar()
        dm_entry = tk.Entry(dm_input_frame, textvariable=self.dm_var, font=FT,
                            bg=C['input_bg'], fg=C['text'],
                            insertbackground=C['accent'], relief='flat', bd=6)
        dm_entry.pack(fill='x', padx=8, pady=(8, 4))
        dm_entry.bind('<Return>', lambda e: self._admin_dm())
        tk.Button(dm_input_frame, text='Send DM 💬', font=FB,
                  bg='#4a1d96', fg='white', relief='flat', bd=0,
                  padx=10, pady=6, cursor='hand2',
                  command=self._admin_dm).pack(fill='x', padx=8, pady=(0, 4))

        if self._enc_enabled:
            tk.Label(dm_input_frame, text='🔐 DM will be encrypted',
                     font=('Segoe UI', 8), bg=C['panel'],
                     fg=C['success']).pack(anchor='w', padx=8, pady=(0, 4))

        # Broadcast section
        sep2 = tk.Frame(left, bg=C['border'], height=1); sep2.pack(fill='x', padx=8, pady=4)
        bc_frame = tk.Frame(left, bg=C['panel']); bc_frame.pack(fill='x', padx=8, pady=4)
        tk.Label(bc_frame, text='📢 Broadcast to All', font=FB,
                 bg=C['panel'], fg=C['accent2']).pack(anchor='w', padx=8, pady=(8, 4))
        self.bc_var = tk.StringVar()
        bc_entry = tk.Entry(bc_frame, textvariable=self.bc_var, font=FT,
                            bg=C['input_bg'], fg=C['text'],
                            insertbackground=C['accent'], relief='flat', bd=6)
        bc_entry.pack(fill='x', padx=8, pady=(0, 4))
        bc_entry.bind('<Return>', lambda e: self._admin_broadcast())
        tk.Button(bc_frame, text='Send to All 📢', font=FB,
                  bg=C['accent'], fg='white', relief='flat', bd=0,
                  padx=10, pady=6, cursor='hand2',
                  command=self._admin_broadcast).pack(fill='x', padx=8, pady=(0, 4))
        tk.Button(bc_frame, text='Send File to All 📁', font=FS,
                  bg=C['panel'], fg=C['accent2'], relief='flat', bd=0,
                  padx=10, pady=6, cursor='hand2',
                  command=self._admin_send_file).pack(fill='x', padx=8, pady=(0, 8))

        # ── Right panel — Tabs ──
        right = tk.Frame(content, bg=C['bg']); right.pack(side='left', fill='both', expand=True)

        tab_frame = tk.Frame(right, bg=C['panel']); tab_frame.pack(fill='x')
        self.active_tab = tk.StringVar(value='messages')
        for label, val in [('💬 All Messages', 'messages'),
                            ('🔒 DM Monitor', 'dm_monitor'),
                            ('📋 Logs', 'logs'),
                            ('👥 Groups', 'groups')]:
            tk.Radiobutton(tab_frame, text=label, variable=self.active_tab, value=val,
                           bg=C['panel'], fg=C['text'], selectcolor=C['accent'],
                           activebackground=C['panel'], font=FT,
                           indicatoron=False, relief='flat', padx=14, pady=8,
                           cursor='hand2',
                           command=self._switch_tab).pack(side='left')

        # Messages tab
        self.msg_frame = tk.Frame(right, bg=C['bg'])
        self.msg_frame.pack(fill='both', expand=True)
        msg_wrap = tk.Frame(self.msg_frame, bg=C['bg']); msg_wrap.pack(fill='both', expand=True)
        self.msg_text = tk.Text(msg_wrap, state='disabled', wrap='word',
                                bg=C['bg'], fg=C['text'], font=FT,
                                relief='flat', bd=0, padx=14, pady=10, spacing3=3)
        vsb = ttk.Scrollbar(msg_wrap, command=self.msg_text.yview)
        self.msg_text.configure(yscrollcommand=vsb.set)
        vsb.pack(side='right', fill='y'); self.msg_text.pack(fill='both', expand=True)
        self.msg_text.tag_config('admin',   foreground=C['warn'],    font=FB)
        self.msg_text.tag_config('user',    foreground=C['accent2'], font=FB)
        self.msg_text.tag_config('system',  foreground=C['text_dim'], font=('Segoe UI', 9, 'italic'))
        self.msg_text.tag_config('time',    foreground=C['text_dim'], font=FS)
        self.msg_text.tag_config('text',    foreground=C['text'])
        self.msg_text.tag_config('file_msg',foreground='#34d399',    font=FB)
        self.msg_text.tag_config('dm_tag',  foreground='#f472b6',    font=FB)
        self.msg_text.tag_config('enc_note',foreground=C['success'],  font=('Segoe UI', 8))

        # DM Monitor tab
        self.dm_frame = tk.Frame(right, bg=C['bg'])
        dm_wrap = tk.Frame(self.dm_frame, bg=C['bg']); dm_wrap.pack(fill='both', expand=True)
        self.dm_text = tk.Text(dm_wrap, state='disabled', wrap='word',
                               bg=C['bg'], fg=C['text'], font=FT,
                               relief='flat', bd=0, padx=14, pady=10, spacing3=3)
        dvsb = ttk.Scrollbar(dm_wrap, command=self.dm_text.yview)
        self.dm_text.configure(yscrollcommand=dvsb.set)
        dvsb.pack(side='right', fill='y'); self.dm_text.pack(fill='both', expand=True)
        self.dm_text.tag_config('dm_from', foreground='#f472b6', font=FB)
        self.dm_text.tag_config('time',    foreground=C['text_dim'], font=FS)
        self.dm_text.tag_config('text',    foreground=C['text'])
        self.dm_text.tag_config('admin_dm',foreground=C['warn'],    font=FB)

        # Logs tab
        self.log_frame = tk.Frame(right, bg=C['bg'])
        log_wrap = tk.Frame(self.log_frame, bg=C['bg']); log_wrap.pack(fill='both', expand=True)
        self.log_text = tk.Text(log_wrap, state='disabled', wrap='word',
                                bg=C['bg'], fg=C['online'], font=FM,
                                relief='flat', bd=0, padx=14, pady=10)
        lsb = ttk.Scrollbar(log_wrap, command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=lsb.set)
        lsb.pack(side='right', fill='y'); self.log_text.pack(fill='both', expand=True)

        # Groups tab
        self.groups_frame = tk.Frame(right, bg=C['bg'])
        tk.Label(self.groups_frame, text='Active Private Groups',
                 font=FB, bg=C['bg'], fg=C['accent']).pack(pady=12)
        self.groups_text = tk.Text(self.groups_frame, state='disabled', wrap='word',
                                   bg=C['panel'], fg=C['text'], font=FT,
                                   relief='flat', bd=0, padx=14, pady=10)
        self.groups_text.pack(fill='both', expand=True, padx=16, pady=(0, 16))

        self._switch_tab()

    def _switch_tab(self):
        self.msg_frame.pack_forget()
        self.dm_frame.pack_forget()
        self.log_frame.pack_forget()
        self.groups_frame.pack_forget()
        tab = self.active_tab.get()
        if tab == 'messages':
            self.msg_frame.pack(fill='both', expand=True)
        elif tab == 'dm_monitor':
            self.dm_frame.pack(fill='both', expand=True)
        elif tab == 'logs':
            self.log_frame.pack(fill='both', expand=True)
        elif tab == 'groups':
            self.groups_frame.pack(fill='both', expand=True)
            self._refresh_groups()

    def _refresh_groups(self):
        self.groups_text.config(state='normal')
        self.groups_text.delete('1.0', 'end')
        if not self.server.groups:
            self.groups_text.insert('end', 'No groups created yet.\n')
        else:
            for g in self.server.groups.values():
                self.groups_text.insert('end',
                    f'👥  {g["name"]}\n'
                    f'    Creator : {g["creator"]}\n'
                    f'    Members : {", ".join(sorted(g["members"]))}\n'
                    f'    Count   : {len(g["members"])} members\n\n')
        self.groups_text.config(state='disabled')

    # ── User list ──────────────────────────────────────────────────────
    def _refresh_users(self):
        for w in self.user_frame.winfo_children():
            w.destroy()
        users = self.server._all_users()
        self.user_count_label.config(
            text=f'{len(users)} user{"s" if len(users)!=1 else ""} online')
        for u in users:
            uname = u['username']
            blocked = u.get('blocked', False)
            is_dm_target = (uname == self._dm_target)

            row = tk.Frame(self.user_frame,
                           bg=C['dm_bg'] if is_dm_target else C['sidebar'])
            row.pack(fill='x', padx=6, pady=2)

            cv = tk.Canvas(row, width=26, height=26,
                           bg=C['dm_bg'] if is_dm_target else C['sidebar'],
                           highlightthickness=0)
            cv.pack(side='left', padx=(4, 6))
            cv.create_oval(1, 1, 25, 25,
                           fill=u.get('avatar_color', C['accent']), outline='')
            cv.create_text(13, 13, text=uname[:2].upper(),
                           fill='white', font=('Segoe UI', 9, 'bold'))

            color = C['danger'] if blocked else (C['accent'] if is_dm_target else C['online'])
            status = ' 🚫' if blocked else (' 💬' if is_dm_target else '')
            tk.Label(row, text=f'{uname}{status}', font=FS,
                     bg=C['dm_bg'] if is_dm_target else C['sidebar'],
                     fg=color).pack(side='left', fill='x', expand=True)

            btns = tk.Frame(row, bg=C['dm_bg'] if is_dm_target else C['sidebar'])
            btns.pack(side='right')

            # DM button
            tk.Button(btns, text='💬', font=FS,
                      bg=C['dm_bg'] if is_dm_target else C['sidebar'],
                      fg=C['accent'], relief='flat', bd=0, padx=3,
                      cursor='hand2',
                      command=lambda n=uname: self._select_dm_target(n)
                      ).pack(side='left')

            if blocked:
                tk.Button(btns, text='✅', font=FS,
                          bg=C['sidebar'], fg=C['success'],
                          relief='flat', bd=0, padx=3, cursor='hand2',
                          command=lambda n=uname: self._unblock(n)).pack(side='left')
            else:
                tk.Button(btns, text='🚫', font=FS,
                          bg=C['sidebar'], fg=C['danger'],
                          relief='flat', bd=0, padx=3, cursor='hand2',
                          command=lambda n=uname: self._block(n)).pack(side='left')

            tk.Button(btns, text='👢', font=FS,
                      bg=C['sidebar'], fg=C['warn'],
                      relief='flat', bd=0, padx=3, cursor='hand2',
                      command=lambda n=uname: self._kick(n)).pack(side='left')

    def _refresh_loop(self):
        self._refresh_users()
        self.after(2000, self._refresh_loop)

    # ── DM to user ─────────────────────────────────────────────────────
    def _select_dm_target(self, username):
        self._dm_target = username
        self.dm_target_label.config(
            text=f'Sending DM to: {username}',
            fg=C['accent2'])
        self.dm_var.get()  # just to refresh

    def _admin_dm(self):
        if not self._dm_target:
            messagebox.showwarning('No Target',
                                   'Click 💬 next to a user first to select DM target.',
                                   parent=self)
            return
        text = self.dm_var.get().strip()
        if not text:
            return
        ok = self.server.admin_dm(self._dm_target, text,
                                   encrypted=self._enc_enabled)
        if ok:
            ts = datetime.now().strftime('%H:%M')
            self._append_dm_monitor('📢 ADMIN', self._dm_target, text, ts)
            self.dm_var.set('')
        else:
            messagebox.showerror('Failed',
                                 f'User "{self._dm_target}" not found or disconnected.',
                                 parent=self)

    # ── Broadcast ──────────────────────────────────────────────────────
    def _admin_broadcast(self):
        text = self.bc_var.get().strip()
        if not text:
            return
        self.server.admin_broadcast(text, encrypted=self._enc_enabled)
        self.bc_var.set('')

    def _admin_send_file(self):
        path = filedialog.askopenfilename(title='Select File to Broadcast')
        if not path:
            return
        ok, msg = self.server.admin_send_file(path)
        if ok:
            messagebox.showinfo('Sent', msg, parent=self)
        else:
            messagebox.showerror('Error', msg, parent=self)

    # ── Block/Unblock/Kick ─────────────────────────────────────────────
    def _block(self, username):
        if messagebox.askyesno('Block', f'Block {username}?', parent=self):
            self.server.admin_block(username)

    def _unblock(self, username):
        self.server.admin_unblock(username)

    def _kick(self, username):
        if messagebox.askyesno('Kick', f'Kick {username}?', parent=self):
            self.server.admin_kick(username)

    # ── Message display ────────────────────────────────────────────────
    def _append_to(self, widget, fn):
        def _do():
            widget.config(state='normal')
            fn(widget)
            widget.config(state='disabled')
            widget.see('end')
        self.after(0, _do)

    def _append_msg_monitor(self, sender, text, time_str,
                             is_admin=False, is_system=False,
                             is_file=False, is_dm=False,
                             enc_decrypted=False):
        def _do(w):
            if is_system:
                w.insert('end', f'  {text}\n', 'system')
            elif is_file:
                w.insert('end', f'  {time_str}  ', 'time')
                w.insert('end', f'{sender}', 'file_msg')
                w.insert('end', f':  📎 {text}\n', 'text')
            elif is_dm:
                w.insert('end', f'  {time_str}  ', 'time')
                w.insert('end', f'[DM] {sender}', 'dm_tag')
                w.insert('end', f':  {text}', 'text')
                if enc_decrypted:
                    w.insert('end', '  🔐', 'enc_note')
                w.insert('end', '\n')
            else:
                tag = 'admin' if is_admin else 'user'
                w.insert('end', f'  {time_str}  ', 'time')
                w.insert('end', f'{sender}', tag)
                w.insert('end', f':  {text}', 'text')
                if enc_decrypted:
                    w.insert('end', '  🔐', 'enc_note')
                w.insert('end', '\n')
        self._append_to(self.msg_text, _do)

    def _append_dm_monitor(self, sender, target, text, time_str, is_admin=False):
        def _do(w):
            tag = 'admin_dm' if is_admin else 'dm_from'
            w.insert('end', f'  {time_str}  ', 'time')
            w.insert('end', f'{sender}', tag)
            w.insert('end', f' → {target}:  {text}\n', 'text')
        self._append_to(self.dm_text, _do)

    def _log_line(self, line):
        def _do(w):
            ts = datetime.now().strftime('%H:%M:%S')
            w.insert('end', f'[{ts}] {line}\n')
        self._append_to(self.log_text, _do)

    # ── Server event callback ──────────────────────────────────────────
    def _on_server_event(self, event_type, data):
        if event_type == 'message':
            display = data.get('display_text', data.get('text', ''))
            enc_dec = data.get('encrypted', False) and bool(self.server.enc_key)
            self._append_msg_monitor(
                data['from'], display, data.get('time', ''),
                is_admin=data.get('is_admin', False),
                enc_decrypted=enc_dec)

        elif event_type == 'private_msg':
            self._append_msg_monitor(
                f'{data["from"]}→{data["to"]}',
                data['text'], data.get('time', ''), is_dm=True)
            self._append_dm_monitor(
                data['from'], data['to'], data['text'], data.get('time', ''))

        elif event_type == 'admin_dm':
            self._append_dm_monitor(
                '📢 ADMIN', data['to'], data['text'],
                data.get('time', ''), is_admin=True)
            status = '✅ Delivered' if data.get('ok') else '❌ User not found'
            self._log_line(f'Admin DM → {data["to"]}: {data["text"]} [{status}]')

        elif event_type == 'log':
            self._log_line(data)

        elif event_type == 'user_join':
            self._append_msg_monitor(
                '', f'{data["username"]} joined from {data["addr"]}',
                '', is_system=True)

        elif event_type == 'user_leave':
            self._append_msg_monitor(
                '', f'{data["username"]} left the chat', '', is_system=True)

        elif event_type == 'file':
            self._append_msg_monitor(
                data['from'], data['filename'],
                datetime.now().strftime('%H:%M'), is_file=True)

        elif event_type == 'group_created':
            self._append_msg_monitor(
                '',
                f'Group "{data["name"]}" created by {data["creator"]} '
                f'({len(data["members"])} members)',
                '', is_system=True)

    def _on_close(self):
        if messagebox.askyesno('Quit', 'Stop server and quit?', parent=self):
            try:
                self.server.server_socket.close()
            except Exception:
                pass
            self.destroy()


if __name__ == '__main__':
    import sys as _sys
    # Support: python server.py 9090 mypassword
    # These will be pre-filled in the admin login dialog
    _port = int(_sys.argv[1]) if len(_sys.argv) > 1 else 9090
    _room_pw = _sys.argv[2] if len(_sys.argv) > 2 else ''
    if _port != 9090:
        # patch default port
        ChatServer.DEFAULT_PORT = _port
    if _room_pw:
        # Pre-set so admin login can show it
        _CMDLINE_ROOM_PW = _room_pw
        print(f'Room password set from command line.')
    else:
        _CMDLINE_ROOM_PW = ''
    app = AdminPanel(cmdline_room_pw=_CMDLINE_ROOM_PW, cmdline_port=_port)
    app.mainloop()
