"""
LAN Chat Client v5
New: Private Group Chat, Admin Broadcast display, Block notifications
"""

import socket, threading, json, tkinter as tk
from tkinter import ttk, messagebox, filedialog, simpledialog
from datetime import datetime
from collections import Counter
import sys, os, base64, wave, struct, math, tempfile, time

try:
    import winsound
    HAS_WINSOUND = True
except ImportError:
    HAS_WINSOUND = False

try:
    from crypto_utils import encrypt, decrypt, derive_key
    HAS_CRYPTO = True
except ImportError:
    HAS_CRYPTO = False

DISCOVERY_PORT = 9091

# ══════════════════════════════════════════════════════════════════════
#  THEMES
# ══════════════════════════════════════════════════════════════════════
THEMES = {
    'Dark': {
        'bg':'#1a1d2e','sidebar':'#13152a','panel':'#1f2235',
        'input_bg':'#252840','accent':'#7c6af7','accent2':'#5eead4',
        'text':'#e2e8f0','text_dim':'#8892a4','online':'#4ade80',
        'border':'#2e3250','hover':'#2a2d45','suggest_bg':'#2a2d45',
        'typing_fg':'#94a3b8','pin_bg':'#2d2a50','search_hl':'#f59e0b',
        'reply_bg':'#1e2038','group_bg':'#1a2a1a','admin_bg':'#2a1a3a',
    },
    'Light': {
        'bg':'#f8fafc','sidebar':'#e8edf5','panel':'#ffffff',
        'input_bg':'#f1f5f9','accent':'#6366f1','accent2':'#0ea5e9',
        'text':'#1e293b','text_dim':'#64748b','online':'#22c55e',
        'border':'#cbd5e1','hover':'#e2e8f0','suggest_bg':'#f1f5f9',
        'typing_fg':'#64748b','pin_bg':'#ede9fe','search_hl':'#fbbf24',
        'reply_bg':'#f0f4ff','group_bg':'#f0fff0','admin_bg':'#fdf0ff',
    },
    'Hacker': {
        'bg':'#0d0d0d','sidebar':'#0a0a0a','panel':'#111111',
        'input_bg':'#1a1a1a','accent':'#00ff41','accent2':'#00ccff',
        'text':'#00ff41','text_dim':'#006600','online':'#00ff41',
        'border':'#003300','hover':'#001a00','suggest_bg':'#0d1a0d',
        'typing_fg':'#009900','pin_bg':'#001a00','search_hl':'#ffff00',
        'reply_bg':'#001100','group_bg':'#001a00','admin_bg':'#1a0030',
    },
}
C = dict(THEMES['Dark'])

def apply_theme(name):
    C.update(THEMES.get(name, THEMES['Dark']))

FONT_MAIN  = ('Segoe UI', 10)
FONT_BOLD  = ('Segoe UI', 10, 'bold')
FONT_SMALL = ('Segoe UI', 9)
FONT_TITLE = ('Segoe UI', 14, 'bold')

AVATAR_COLORS = ['#7c6af7','#f472b6','#fb923c','#34d399','#60a5fa',
                 '#facc15','#a78bfa','#f87171','#4ade80','#38bdf8']
QUICK_REACTIONS = ['👍','❤️','😂','😮','😢','🔥','👏','🎉']
EMOJI_CATEGORIES = {
    '😊':['😀','😃','😄','😁','😆','😅','😂','🤣','😊','😇','🙂','😉','😍','🥰','😘','😋','😛','😜','🤪','😎'],
    '👍':['👍','👎','👌','✌️','🤞','🤟','🤘','🤙','👈','👉','👆','👇','☝️','👋','🤚','🖐️','✋','💪','🙏','👏'],
    '❤️':['❤️','🧡','💛','💚','💙','💜','🖤','🤍','💔','💕','💞','💓','💗','💖','💘','💝','😻','💑','👫','🥂'],
    '🎉':['🎉','🎊','🎈','🎁','🏆','🥇','🎯','🎮','🎲','🎸','🎵','🎶','🎤','🥳','🍾','🥂','🍻','🎂','🕯️','✨'],
    '💡':['💡','🔥','✨','💫','⚡','🌈','⭐','🌙','☀️','❄️','🌊','🌸','🌺','🍀','🌿','🌲','🔑','🔒','💊','🔭'],
}


# ══════════════════════════════════════════════════════════════════════
#  SOUND
# ══════════════════════════════════════════════════════════════════════
def play_notification():
    try:
        if HAS_WINSOUND:
            winsound.MessageBeep(winsound.MB_OK); return
        import subprocess
        freq,dur,vol=880,0.15,0.4; sr=44100; n=int(sr*dur)
        wp=os.path.join(tempfile.gettempdir(),'_lc5.wav')
        with wave.open(wp,'w') as wf:
            wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(sr)
            frames=[]
            for i in range(n):
                t=i/sr; env=math.sin(math.pi*t/dur)
                frames.append(struct.pack('<h',int(32767*vol*env*math.sin(2*math.pi*freq*t))))
            wf.writeframes(b''.join(frames))
        if sys.platform=='darwin':
            subprocess.Popen(['afplay',wp],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        else:
            subprocess.Popen(['aplay','-q',wp],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    except Exception:
        pass


# ══════════════════════════════════════════════════════════════════════
#  SUGGESTION ENGINE
# ══════════════════════════════════════════════════════════════════════
class SuggestionEngine:
    def __init__(self):
        self.word_freq=Counter(); self.bigram_freq=Counter(); self.sent_phrases=[]
    def feed(self,text):
        text=text.strip()
        if not text: return
        self.sent_phrases.append(text)
        words=text.lower().split()
        for w in words: self.word_freq[w]+=1
        for i in range(len(words)-1): self.bigram_freq[(words[i],words[i+1])]+=1
    def suggest(self,current_text,n=5):
        if not current_text.strip():
            pf=Counter()
            for p in self.sent_phrases: pf[p]+=1
            return [p for p,_ in pf.most_common(n)]
        words=current_text.split(); ends_space=current_text.endswith(' ')
        if not ends_space:
            partial=words[-1].lower(); prev=words[-2].lower() if len(words)>=2 else None
            cands=[]
            if prev:
                bc=[(nw,c) for (pw,nw),c in self.bigram_freq.items() if pw==prev and nw.startswith(partial) and nw!=partial]
                bc.sort(key=lambda x:-x[1]); cands+=[nw for nw,_ in bc]
            fc=[(w,c) for w,c in self.word_freq.items() if w.startswith(partial) and w!=partial and w not in cands]
            fc.sort(key=lambda x:-x[1]); cands+=[w for w,_ in fc]
            pfx=current_text[:current_text.rfind(words[-1])]
            return [(pfx+c) for c in cands[:n]]
        else:
            lw=words[-1].lower() if words else ''
            bc=[(nw,c) for (pw,nw),c in self.bigram_freq.items() if pw==lw]
            bc.sort(key=lambda x:-x[1])
            suggs=[current_text+nw for nw,_ in bc[:n]]
            if len(suggs)<n:
                cm=[w for w,_ in self.word_freq.most_common(20) if w!=lw and (current_text+w) not in suggs]
                suggs+=[current_text+w for w in cm[:n-len(suggs)]]
            return suggs[:n]


# ══════════════════════════════════════════════════════════════════════
#  NETWORK
# ══════════════════════════════════════════════════════════════════════
class ChatClient:
    def __init__(self,host,port,username,avatar_color,on_message,on_disconnect):
        self.host=host; self.port=port; self.username=username
        self.avatar_color=avatar_color
        self.on_message=on_message; self.on_disconnect=on_disconnect
        self.sock=socket.socket(socket.AF_INET,socket.SOCK_STREAM)
        self.connected=False; self._buf=''

    def connect(self,room_password='',user_password=''):
        self.sock.connect((self.host,self.port))
        self.connected=True
        self._send({'type':'join','username':self.username,
                    'avatar_color':self.avatar_color,
                    'room_password':room_password,
                    'user_password':user_password})
        threading.Thread(target=self._recv_loop,daemon=True).start()

    def _send(self,obj):
        try: self.sock.sendall((json.dumps(obj)+'\n').encode('utf-8'))
        except Exception: pass

    def send_message(self,text,encrypted=False,reply_to=None):
        self._send({'type':'message','text':text,'encrypted':encrypted,'reply_to':reply_to})

    def send_private(self,target,text,encrypted=False,reply_to=None):
        self._send({'type':'private','to':target,'text':text,'encrypted':encrypted,'reply_to':reply_to})

    def send_group_message(self,group_id,text,encrypted=False):
        self._send({'type':'group_message','group_id':group_id,'text':text,'encrypted':encrypted})

    def create_group(self,group_name,members):
        self._send({'type':'create_group','group_name':group_name,'members':members})

    def send_typing(self,is_typing): self._send({'type':'typing','is_typing':is_typing})

    def send_file(self,filepath,target=None):
        fn=os.path.basename(filepath)
        with open(filepath,'rb') as f: data=f.read()
        payload={'type':'file','filename':fn,'filesize':len(data),
                 'filedata':base64.b64encode(data).decode()}
        if target: payload['to']=target
        self._send(payload)

    def edit_message(self,msg_id,new_text): self._send({'type':'edit','msg_id':msg_id,'text':new_text})
    def delete_message(self,msg_id): self._send({'type':'delete','msg_id':msg_id})
    def react(self,msg_id,emoji): self._send({'type':'react','msg_id':msg_id,'emoji':emoji})
    def mark_read(self,msg_id): self._send({'type':'read','msg_id':msg_id})
    def pin_message(self,text): self._send({'type':'pin','text':text})
    def unpin_message(self,index): self._send({'type':'unpin','index':index})
    def request_stats(self): self._send({'type':'get_stats'})

    def _recv_loop(self):
        try:
            while True:
                chunk=self.sock.recv(65536).decode('utf-8',errors='replace')
                if not chunk: break
                self._buf+=chunk
                while '\n' in self._buf:
                    line,self._buf=self._buf.split('\n',1)
                    if line.strip():
                        try: self.on_message(json.loads(line))
                        except Exception: pass
        except Exception: pass
        finally:
            self.connected=False; self.on_disconnect()

    def disconnect(self):
        try: self.sock.close()
        except Exception: pass


# ══════════════════════════════════════════════════════════════════════
#  UDP DISCOVER
# ══════════════════════════════════════════════════════════════════════
def discover_servers(timeout=2.5):
    servers=[]
    try:
        udp=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
        udp.setsockopt(socket.SOL_SOCKET,socket.SO_BROADCAST,1)
        udp.settimeout(timeout)
        udp.sendto(b'LANCHAT_DISCOVER',('<broadcast>',DISCOVERY_PORT))
        deadline=time.time()+timeout
        while time.time()<deadline:
            try:
                data,addr=udp.recvfrom(512)
                info=json.loads(data.decode())
                if info.get('service')=='lanchat' and info not in servers:
                    servers.append(info)
            except socket.timeout: break
            except Exception: pass
        udp.close()
    except Exception: pass
    return servers


# ══════════════════════════════════════════════════════════════════════
#  EMOJI PICKER
# ══════════════════════════════════════════════════════════════════════
class EmojiPicker(tk.Toplevel):
    def __init__(self,parent,on_select):
        super().__init__(parent)
        self.on_select=on_select; self.title('Emoji')
        self.resizable(False,False); self.configure(bg=C['bg'])
        self.geometry('340x260'); self.transient(parent); self._build()
    def _build(self):
        tab=tk.Frame(self,bg=C['sidebar']); tab.pack(fill='x')
        self.ef=tk.Frame(self,bg=C['panel']); self.ef.pack(fill='both',expand=True,padx=4,pady=4)
        cats=list(EMOJI_CATEGORIES.keys())
        for cat in cats:
            tk.Button(tab,text=cat,font=('Segoe UI',13),bg=C['sidebar'],fg=C['text'],
                      relief='flat',bd=0,padx=6,pady=4,cursor='hand2',
                      command=lambda c=cat:self._show(c)).pack(side='left')
        self._show(cats[0])
    def _show(self,cat):
        for w in self.ef.winfo_children(): w.destroy()
        for i,e in enumerate(EMOJI_CATEGORIES[cat]):
            r,col=divmod(i,10)
            tk.Button(self.ef,text=e,font=('Segoe UI',15),bg=C['panel'],relief='flat',bd=0,
                      padx=2,pady=2,cursor='hand2',activebackground=C['hover'],
                      command=lambda x=e:self._pick(x)).grid(row=r,column=col,padx=1,pady=1)
    def _pick(self,e):
        self.on_select(e); self.destroy()


# ══════════════════════════════════════════════════════════════════════
#  CREATE GROUP DIALOG
# ══════════════════════════════════════════════════════════════════════
class CreateGroupDialog(tk.Toplevel):
    def __init__(self,parent,users,my_username):
        super().__init__(parent)
        self.result=None; self.my_username=my_username
        self.title('👥 Create Private Group')
        self.configure(bg=C['bg']); self.geometry('380x420')
        self.resizable(False,False); self.transient(parent); self.grab_set()
        self._build(users)
        self.after(100,self._center)

    def _center(self):
        self.update_idletasks()
        x=(self.winfo_screenwidth()-self.winfo_width())//2
        y=(self.winfo_screenheight()-self.winfo_height())//2
        self.geometry(f'+{x}+{y}')

    def _build(self,users):
        tk.Label(self,text='👥 Create Private Group',font=FONT_BOLD,
                 bg=C['bg'],fg=C['accent']).pack(pady=(16,8))

        tk.Label(self,text='Group Name:',font=FONT_SMALL,
                 bg=C['bg'],fg=C['text_dim']).pack(anchor='w',padx=20)
        self.name_var=tk.StringVar()
        tk.Entry(self,textvariable=self.name_var,font=FONT_MAIN,
                 bg=C['input_bg'],fg=C['text'],insertbackground=C['accent'],
                 relief='flat',bd=6).pack(fill='x',padx=20,pady=(0,12))

        tk.Label(self,text='Select Members (Ctrl+Click for multiple):',
                 font=FONT_SMALL,bg=C['bg'],fg=C['text_dim']).pack(anchor='w',padx=20)

        lb_frame=tk.Frame(self,bg=C['bg']); lb_frame.pack(fill='both',expand=True,padx=20,pady=4)
        self.lb=tk.Listbox(lb_frame,selectmode='multiple',font=FONT_MAIN,
                           bg=C['input_bg'],fg=C['text'],
                           selectbackground=C['accent'],
                           relief='flat',bd=0,activestyle='none')
        lsb=ttk.Scrollbar(lb_frame,command=self.lb.yview)
        self.lb.configure(yscrollcommand=lsb.set)
        lsb.pack(side='right',fill='y'); self.lb.pack(fill='both',expand=True)

        # Add users except self
        self.user_list=[u for u in users if u!=self.my_username]
        for u in self.user_list:
            self.lb.insert('end',f'  {u}')

        btn_f=tk.Frame(self,bg=C['bg']); btn_f.pack(fill='x',padx=20,pady=12)
        tk.Button(btn_f,text='Cancel',font=FONT_MAIN,bg=C['panel'],fg=C['text_dim'],
                  relief='flat',bd=0,padx=14,pady=8,cursor='hand2',
                  command=self.destroy).pack(side='left')
        tk.Button(btn_f,text='Create Group ✅',font=FONT_BOLD,
                  bg=C['accent'],fg='white',relief='flat',bd=0,
                  padx=14,pady=8,cursor='hand2',
                  command=self._create).pack(side='right')

    def _create(self):
        name=self.name_var.get().strip()
        if not name:
            messagebox.showerror('Error','Please enter a group name.',parent=self); return
        selected=[self.user_list[i] for i in self.lb.curselection()]
        if not selected:
            messagebox.showerror('Error','Select at least one member.',parent=self); return
        self.result={'name':name,'members':selected}
        self.destroy()


# ══════════════════════════════════════════════════════════════════════
#  LOGIN DIALOG
# ══════════════════════════════════════════════════════════════════════
class LoginDialog(tk.Toplevel):
    def __init__(self,parent):
        super().__init__(parent)
        self.result=None; self.title('LAN Chat v5 — Connect')
        self.resizable(False,False); self.configure(bg=C['bg'])
        self.grab_set(); self._discovered=[]; self._build()
        self.protocol('WM_DELETE_WINDOW',self._cancel)
        self.after(100,self._center)

    def _center(self):
        self.update_idletasks()
        x=(self.winfo_screenwidth()-self.winfo_width())//2
        y=(self.winfo_screenheight()-self.winfo_height())//2
        self.geometry(f'+{x}+{y}')

    def _build(self):
        tk.Label(self,text='🌐 LAN Chat v5',font=FONT_TITLE,
                 bg=C['bg'],fg=C['accent']).pack(pady=(20,2))
        tk.Label(self,text='Admin Panel · Groups · Broadcast · Block/Unblock',
                 font=FONT_SMALL,bg=C['bg'],fg=C['text_dim']).pack(pady=(0,10))

        tf=tk.Frame(self,bg=C['bg']); tf.pack()
        tk.Label(tf,text='Theme:',font=FONT_SMALL,bg=C['bg'],fg=C['text_dim']).pack(side='left',padx=4)
        self.theme_var=tk.StringVar(value='Dark')
        for t in THEMES:
            tk.Radiobutton(tf,text=t,variable=self.theme_var,value=t,
                           bg=C['bg'],fg=C['text'],selectcolor=C['input_bg'],
                           activebackground=C['bg'],font=FONT_SMALL).pack(side='left',padx=4)

        frame=tk.Frame(self,bg=C['panel']); frame.pack(fill='x',padx=24,pady=8)

        def field(lbl,default='',show=None):
            tk.Label(frame,text=lbl,font=FONT_SMALL,bg=C['panel'],fg=C['text_dim'],anchor='w').pack(fill='x',padx=18,pady=(6,0))
            e=tk.Entry(frame,font=FONT_MAIN,bg=C['input_bg'],fg=C['text'],
                       insertbackground=C['accent'],relief='flat',bd=6,show=show)
            e.insert(0,default); e.pack(fill='x',padx=18,pady=(0,4))
            return e

        self.host_e=field('Server IP','127.0.0.1')
        self.port_e=field('Port','9090')
        self.name_e=field('Username',''); self.name_e.focus_set()
        self.user_pass_e=field('Account Password (optional)','',show='•')
        self.room_pass_e=field('Room Password (if locked)','',show='•')
        self.enc_e=field('Encryption Passphrase (same on all devices)','',show='•')

        ac=tk.Frame(frame,bg=C['panel']); ac.pack(fill='x',padx=18,pady=(4,8))
        tk.Label(ac,text='Avatar:',font=FONT_SMALL,bg=C['panel'],fg=C['text_dim']).pack(side='left')
        self.avatar_color=tk.StringVar(value=AVATAR_COLORS[0])
        for col in AVATAR_COLORS:
            tk.Radiobutton(ac,variable=self.avatar_color,value=col,bg=col,
                           selectcolor=col,activebackground=col,
                           indicatoron=False,width=2,relief='flat',cursor='hand2').pack(side='left',padx=2)

        self.sound_var=tk.BooleanVar(value=True)
        tk.Checkbutton(frame,text=' Sound notifications',variable=self.sound_var,
                       bg=C['panel'],fg=C['text_dim'],selectcolor=C['input_bg'],
                       activebackground=C['panel'],font=FONT_SMALL).pack(anchor='w',padx=18,pady=(0,10))

        df=tk.Frame(self,bg=C['bg']); df.pack(fill='x',padx=24,pady=(0,4))
        tk.Button(df,text='📡 Auto-Discover',font=FONT_SMALL,bg=C['panel'],fg=C['accent2'],
                  relief='flat',bd=0,padx=12,pady=6,cursor='hand2',
                  command=self._discover).pack(side='left')
        self.disc_lbl=tk.Label(df,text='',font=FONT_SMALL,bg=C['bg'],fg=C['text_dim'])
        self.disc_lbl.pack(side='left',padx=8)
        self.disc_lb=tk.Listbox(self,font=FONT_SMALL,bg=C['input_bg'],fg=C['text'],
                                selectbackground=C['accent'],relief='flat',height=0,bd=0)
        self.disc_lb.bind('<<ListboxSelect>>',self._on_disc_sel)

        bf=tk.Frame(self,bg=C['bg']); bf.pack(fill='x',padx=24,pady=12)
        tk.Button(bf,text='Cancel',font=FONT_MAIN,bg=C['panel'],fg=C['text_dim'],
                  relief='flat',bd=0,padx=14,pady=8,cursor='hand2',
                  command=self._cancel).pack(side='left')
        tk.Button(bf,text='Connect →',font=FONT_BOLD,bg=C['accent'],fg='white',
                  relief='flat',bd=0,padx=18,pady=8,cursor='hand2',
                  command=self._connect).pack(side='right')
        self.bind('<Return>',lambda e:self._connect())

    def _discover(self):
        self.disc_lbl.config(text='Scanning…'); self.update()
        servers=discover_servers(2.5); self._discovered=servers
        if servers:
            self.disc_lb.delete(0,'end')
            for s in servers:
                self.disc_lb.insert('end',f"  {s['name']}  ({s['ip']}:{s['port']})")
            self.disc_lb.config(height=min(len(servers),4))
            self.disc_lb.pack(fill='x',padx=24,pady=2)
            self.disc_lbl.config(text=f'{len(servers)} found')
        else:
            self.disc_lb.pack_forget(); self.disc_lbl.config(text='No servers found')

    def _on_disc_sel(self,event):
        sel=self.disc_lb.curselection()
        if sel:
            s=self._discovered[sel[0]]
            self.host_e.delete(0,'end'); self.host_e.insert(0,s['ip'])
            self.port_e.delete(0,'end'); self.port_e.insert(0,str(s['port']))

    def _connect(self):
        host=self.host_e.get().strip(); port=self.port_e.get().strip()
        name=self.name_e.get().strip()
        if not host or not port or not name:
            messagebox.showerror('Error','IP, Port and Username required.',parent=self); return
        try: port=int(port)
        except ValueError:
            messagebox.showerror('Error','Port must be a number.',parent=self); return
        self.result={
            'host':host,'port':port,'username':name,
            'user_password':self.user_pass_e.get().strip(),
            'room_password':self.room_pass_e.get().strip(),
            'passphrase':self.enc_e.get().strip(),
            'avatar_color':self.avatar_color.get(),
            'sound':self.sound_var.get(),
            'theme':self.theme_var.get(),
        }
        self.destroy()

    def _cancel(self):
        self.result=None; self.destroy()


# ══════════════════════════════════════════════════════════════════════
#  MAIN APP
# ══════════════════════════════════════════════════════════════════════
class ChatApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.withdraw()
        self.title('LAN Chat v5')
        self.geometry('1060x700'); self.minsize(820,540)

        self.client=None; self.username=''; self.avatar_color=AVATAR_COLORS[0]
        self.users=[]; self.users_meta={}
        self.suggestion_engine=SuggestionEngine()
        self.dm_target=None          # str username for DM
        self.group_target=None       # dict {id, name} for group chat
        self.sound_enabled=True; self.enc_key=None
        self.pinned=[]; self.history=[]; self.history_file=''
        self._suggest_job=None; self._typing_job=None
        self._is_typing_sent=False; self._typers=set(); self._typer_clears={}
        self._search_highlights=[]; self._search_visible=False
        self._last_stats={}; self._last_users_stat=[]; self._current_theme='Dark'
        self.msg_widgets={}; self.reply_target=None
        self.my_groups={}   # group_id -> {id, name, members}
        self._members_bar=None

        self._build_ui()
        self.after(100,self._show_login)
        self.protocol('WM_DELETE_WINDOW',self._on_close)

    # ── Login ──────────────────────────────────────────────────────────
    def _show_login(self):
        dlg=LoginDialog(self); self.wait_window(dlg)
        if not dlg.result: self.destroy(); return
        r=dlg.result
        apply_theme(r['theme']); self._current_theme=r['theme']
        self.avatar_color=r['avatar_color']; self.sound_enabled=r['sound']
        if r['passphrase'] and HAS_CRYPTO:
            self.enc_key=derive_key(r['passphrase'])
        else:
            self.enc_key=None
        self.username=r['username']
        self._try_connect(r)

    def _try_connect(self,r):
        try:
            self.client=ChatClient(r['host'],r['port'],r['username'],r['avatar_color'],
                                   self._on_server_message,self._on_disconnect)
            self.client.connect(room_password=r.get('room_password',''),
                                user_password=r.get('user_password',''))
            self.title(f'LAN Chat v5  —  {r["username"]}')
            ts=datetime.now().strftime('%Y%m%d_%H%M%S')
            self.history_file=os.path.join(os.path.expanduser('~'),
                                           f'lanchat_v5_{r["username"]}_{ts}.txt')
            self._append_history(f'=== Session started {datetime.now().strftime("%Y-%m-%d %H:%M")} ===')
            self._apply_theme_to_ui(); self.deiconify(); self._center_window()
        except Exception as e:
            messagebox.showerror('Connection Failed',str(e)); self._show_login()

    def _center_window(self):
        self.update_idletasks()
        x=(self.winfo_screenwidth()-self.winfo_width())//2
        y=(self.winfo_screenheight()-self.winfo_height())//2
        self.geometry(f'+{x}+{y}')

    # ── UI ─────────────────────────────────────────────────────────────
    def _build_ui(self):
        self.configure(bg=C['bg'])

        # Sidebar
        self.sidebar=tk.Frame(self,bg=C['sidebar'],width=210)
        self.sidebar.pack(side='left',fill='y'); self.sidebar.pack_propagate(False)

        tk.Label(self.sidebar,text='ONLINE',font=('Segoe UI',8,'bold'),
                 bg=C['sidebar'],fg=C['text_dim'],padx=14,pady=8,anchor='w').pack(fill='x')
        self.user_list_frame=tk.Frame(self.sidebar,bg=C['sidebar'])
        self.user_list_frame.pack(fill='both',expand=True)

        # Groups section in sidebar
        sep=tk.Frame(self.sidebar,bg=C['border'],height=1); sep.pack(fill='x',padx=8,pady=4)
        grp_hdr=tk.Frame(self.sidebar,bg=C['sidebar']); grp_hdr.pack(fill='x')
        tk.Label(grp_hdr,text='GROUPS',font=('Segoe UI',8,'bold'),
                 bg=C['sidebar'],fg=C['text_dim'],padx=14,pady=4,anchor='w').pack(side='left')
        tk.Button(grp_hdr,text='+ New',font=('Segoe UI',8),bg=C['sidebar'],
                  fg=C['accent'],relief='flat',bd=0,cursor='hand2',
                  command=self._create_group_dialog).pack(side='right',padx=8)
        self.groups_frame=tk.Frame(self.sidebar,bg=C['sidebar'])
        self.groups_frame.pack(fill='x')

        # Sidebar bottom buttons
        sb_btns=tk.Frame(self.sidebar,bg=C['sidebar']); sb_btns.pack(fill='x',pady=4,side='bottom')
        tk.Button(sb_btns,text='📊 Stats',font=FONT_SMALL,bg=C['sidebar'],fg=C['accent2'],
                  relief='flat',bd=0,pady=6,cursor='hand2',
                  command=self._show_stats).pack(fill='x',padx=8,pady=2)
        tk.Button(sb_btns,text='🌙 Theme',font=FONT_SMALL,bg=C['sidebar'],fg=C['accent2'],
                  relief='flat',bd=0,pady=6,cursor='hand2',
                  command=self._cycle_theme).pack(fill='x',padx=8,pady=2)

        # Main
        main=tk.Frame(self,bg=C['bg']); main.pack(side='left',fill='both',expand=True)

        # Header
        self.header=tk.Frame(main,bg=C['panel'],height=48)
        self.header.pack(fill='x'); self.header.pack_propagate(False)
        self.header_label=tk.Label(self.header,text='# General',font=FONT_BOLD,
                                   bg=C['panel'],fg=C['text'],padx=14)
        self.header_label.pack(side='left',pady=12)
        self.dm_badge=tk.Label(self.header,text='DM',font=FONT_SMALL,
                               bg=C['accent'],fg='white',padx=8,pady=2)
        self.group_badge=tk.Label(self.header,text='GROUP',font=FONT_SMALL,
                                  bg='#22543d',fg='#4ade80',padx=8,pady=2)
        self.enc_badge=tk.Label(self.header,text='🔐 Encrypted',font=FONT_SMALL,
                                bg='#1a3a1a',fg='#4ade80',padx=8,pady=2)
        hbtns=tk.Frame(self.header,bg=C['panel']); hbtns.pack(side='right',padx=8)
        tk.Button(hbtns,text='💾 Save',font=FONT_SMALL,bg=C['panel'],fg=C['text_dim'],
                  relief='flat',bd=0,padx=8,pady=4,cursor='hand2',
                  command=self._manual_save).pack(side='left',padx=2)
        tk.Button(hbtns,text='🔍 Search',font=FONT_SMALL,bg=C['panel'],fg=C['text_dim'],
                  relief='flat',bd=0,padx=8,pady=4,cursor='hand2',
                  command=self._toggle_search).pack(side='left',padx=2)

        # Pin bar
        self.pin_frame=tk.Frame(main,bg=C['pin_bg'])
        self.pin_label=tk.Label(self.pin_frame,text='',font=FONT_SMALL,
                                bg=C['pin_bg'],fg=C['accent2'],anchor='w',padx=10,pady=4)
        self.pin_label.pack(side='left',fill='x',expand=True)
        tk.Button(self.pin_frame,text='📌 All',font=FONT_SMALL,bg=C['pin_bg'],fg=C['accent'],
                  relief='flat',bd=0,padx=8,cursor='hand2',
                  command=self._show_pins).pack(side='right',padx=4)

        # Search bar
        self.search_frame=tk.Frame(main,bg=C['input_bg'])
        self.search_var=tk.StringVar()
        self.search_var.trace_add('write',self._do_search)
        self.search_entry=tk.Entry(self.search_frame,textvariable=self.search_var,
                                   font=FONT_MAIN,bg=C['input_bg'],fg=C['text'],
                                   insertbackground=C['accent'],relief='flat',bd=6)
        self.search_entry.pack(side='left',fill='x',expand=True,padx=8,pady=6)
        self.search_count=tk.Label(self.search_frame,text='',font=FONT_SMALL,
                                   bg=C['input_bg'],fg=C['text_dim'])
        self.search_count.pack(side='left',padx=4)
        tk.Button(self.search_frame,text='✕',font=FONT_SMALL,bg=C['input_bg'],
                  fg=C['text_dim'],relief='flat',bd=0,padx=8,cursor='hand2',
                  command=self._toggle_search).pack(side='right',padx=4)

        # Reply bar
        self.reply_frame=tk.Frame(main,bg=C['reply_bg'])
        self.reply_label=tk.Label(self.reply_frame,text='',font=FONT_SMALL,
                                  bg=C['reply_bg'],fg=C['accent2'],anchor='w',padx=10,pady=4)
        self.reply_label.pack(side='left',fill='x',expand=True)
        tk.Button(self.reply_frame,text='✕',font=FONT_SMALL,bg=C['reply_bg'],
                  fg=C['text_dim'],relief='flat',bd=0,padx=8,cursor='hand2',
                  command=self._cancel_reply).pack(side='right',padx=4)

        # Chat display
        chat_outer=tk.Frame(main,bg=C['bg']); chat_outer.pack(fill='both',expand=True)
        self.chat_text=tk.Text(chat_outer,state='disabled',wrap='word',
                               bg=C['bg'],fg=C['text'],font=FONT_MAIN,
                               relief='flat',bd=0,padx=12,pady=10,cursor='arrow',
                               selectbackground=C['hover'],spacing3=4)
        vsb=ttk.Scrollbar(chat_outer,command=self.chat_text.yview)
        self.chat_text.configure(yscrollcommand=vsb.set)
        vsb.pack(side='right',fill='y'); self.chat_text.pack(fill='both',expand=True)
        self._setup_tags()
        self.chat_text.bind('<Button-3>',self._on_right_click)

        # Typing bar
        self.typing_label=tk.Label(main,text='',font=('Segoe UI',9,'italic'),
                                   bg=C['bg'],fg=C['typing_fg'],anchor='w',padx=18,pady=2)
        self.typing_label.pack(fill='x')

        # Suggest bar
        self.suggest_frame=tk.Frame(main,bg=C['suggest_bg'],height=32)
        self.suggest_frame.pack(fill='x'); self.suggest_frame.pack_propagate(False)
        self.suggest_buttons=[]

        # Input area
        input_f=tk.Frame(main,bg=C['panel'],pady=10); input_f.pack(fill='x')
        tk.Button(input_f,text='😊',font=('Segoe UI',14),bg=C['panel'],fg=C['text'],
                  relief='flat',bd=0,padx=6,pady=2,cursor='hand2',
                  command=self._open_emoji).pack(side='left',padx=(10,2))
        tk.Button(input_f,text='📁',font=('Segoe UI',14),bg=C['panel'],fg=C['text'],
                  relief='flat',bd=0,padx=6,pady=2,cursor='hand2',
                  command=self._send_file).pack(side='left',padx=(2,2))
        tk.Button(input_f,text='📌',font=('Segoe UI',14),bg=C['panel'],fg=C['text'],
                  relief='flat',bd=0,padx=6,pady=2,cursor='hand2',
                  command=self._pin_current).pack(side='left',padx=(2,4))

        self.input_var=tk.StringVar()
        self.input_var.trace_add('write',self._on_input_change)
        self.input_entry=tk.Entry(input_f,textvariable=self.input_var,
                                  font=FONT_MAIN,bg=C['input_bg'],fg=C['text'],
                                  insertbackground=C['accent'],relief='flat',bd=8)
        self.input_entry.pack(side='left',fill='x',expand=True,padx=(2,8))
        self.input_entry.bind('<Return>',self._send_message)
        self.input_entry.bind('<Tab>',self._tab_complete)
        self.input_entry.bind('<FocusOut>',lambda e:self._stop_typing())

        tk.Button(input_f,text='Send',font=FONT_BOLD,bg=C['accent'],fg='white',
                  relief='flat',bd=0,padx=18,pady=4,cursor='hand2',
                  activebackground='#6455d4',
                  command=self._send_message).pack(side='right',padx=(0,12))

    def _setup_tags(self):
        self.chat_text.tag_config('time',       foreground=C['text_dim'],  font=FONT_SMALL)
        self.chat_text.tag_config('me',         foreground=C['accent'],    font=FONT_BOLD)
        self.chat_text.tag_config('them',       foreground=C['accent2'],   font=FONT_BOLD)
        self.chat_text.tag_config('system',     foreground=C['text_dim'],  font=('Segoe UI',9,'italic'))
        self.chat_text.tag_config('private',    foreground='#f472b6',      font=FONT_BOLD)
        self.chat_text.tag_config('group_msg',  foreground='#4ade80',      font=FONT_BOLD)
        self.chat_text.tag_config('admin_dm',   foreground='#f59e0b',      font=FONT_BOLD)
        self.chat_text.tag_config('admin_msg',  foreground='#f59e0b',      font=FONT_BOLD)
        self.chat_text.tag_config('msg_text',   foreground=C['text'])
        self.chat_text.tag_config('file_msg',   foreground='#34d399',      font=FONT_BOLD)
        self.chat_text.tag_config('enc_tag',    foreground='#4ade80',      font=('Segoe UI',8))
        self.chat_text.tag_config('search_hl',  background=C['search_hl'],foreground='#000000')
        self.chat_text.tag_config('edited_tag', foreground=C['text_dim'],  font=('Segoe UI',8,'italic'))
        self.chat_text.tag_config('deleted',    foreground=C['text_dim'],  font=('Segoe UI',9,'italic'))
        self.chat_text.tag_config('reply_quote',foreground=C['accent2'],   font=('Segoe UI',9,'italic'))
        self.chat_text.tag_config('blocked_warn',foreground='#f87171',     font=('Segoe UI',9,'italic'))

    # ── Theme ──────────────────────────────────────────────────────────
    def _cycle_theme(self):
        themes=list(THEMES.keys())
        idx=(themes.index(self._current_theme)+1)%len(themes)
        self._current_theme=themes[idx]
        apply_theme(self._current_theme); self._apply_theme_to_ui()

    def _apply_theme_to_ui(self):
        self.configure(bg=C['bg']); self._setup_tags()
        self.chat_text.configure(bg=C['bg'],fg=C['text'],selectbackground=C['hover'])

    # ── User list ──────────────────────────────────────────────────────
    def _refresh_user_list(self):
        for w in self.user_list_frame.winfo_children(): w.destroy()
        for u in self.users_meta.values():
            uname=u['username']; is_me=(uname==self.username)
            row=tk.Frame(self.user_list_frame,bg=C['sidebar']); row.pack(fill='x',padx=6,pady=2)
            cv=tk.Canvas(row,width=26,height=26,bg=C['sidebar'],highlightthickness=0)
            cv.pack(side='left',padx=(4,6))
            cv.create_oval(1,1,25,25,fill=u.get('avatar_color',C['accent']),outline='')
            cv.create_text(13,13,text=uname[:2].upper(),fill='white',font=('Segoe UI',9,'bold'))
            blocked=u.get('blocked',False)
            label=uname+(' (you)' if is_me else '')+(' 🚫' if blocked else '')
            fg=C['text_dim'] if blocked else (C['online'] if not is_me else C['text_dim'])
            tk.Button(row,text=label,font=FONT_SMALL,bg=C['sidebar'],fg=fg,
                      relief='flat',bd=0,pady=4,anchor='w',
                      cursor='hand2' if not is_me else 'arrow',
                      activebackground=C['hover'],
                      command=(lambda n=uname:self._start_dm(n)) if not is_me else lambda:None
                      ).pack(side='left',fill='x',expand=True)

        sep=tk.Frame(self.user_list_frame,bg=C['border'],height=1)
        sep.pack(fill='x',pady=4,padx=10)
        tk.Button(self.user_list_frame,text='  # Group chat',font=FONT_SMALL,
                  bg=C['sidebar'],fg=C['accent'],relief='flat',bd=0,pady=6,
                  anchor='w',cursor='hand2',activebackground=C['hover'],
                  command=self._clear_dm).pack(fill='x')

    def _refresh_groups_sidebar(self):
        for w in self.groups_frame.winfo_children(): w.destroy()
        for gid, g in self.my_groups.items():
            btn=tk.Button(self.groups_frame,
                          text=f'  👥 {g["name"]}',
                          font=FONT_SMALL,bg=C['sidebar'],fg=C['accent2'],
                          relief='flat',bd=0,pady=5,anchor='w',cursor='hand2',
                          activebackground=C['hover'],
                          command=lambda gid=gid,g=g:self._open_group(gid,g))
            btn.pack(fill='x')

    def _start_dm(self,target):
        self.dm_target=target; self.group_target=None
        self.header_label.config(text=f'🔒 Private: {target}')
        self.dm_badge.pack(side='left',padx=4)
        self.group_badge.pack_forget()
        self._append_system(f'Now chatting privately with {target}.')

    def _clear_dm(self):
        self.dm_target=None; self.group_target=None
        self.header_label.config(text='# General')
        self.dm_badge.pack_forget(); self.group_badge.pack_forget()
        if hasattr(self,'_members_bar') and self._members_bar:
            try: self._members_bar.pack_forget()
            except Exception: pass
        self._append_system('Back in group chat.')

    def _open_group(self,group_id,group):
        self.group_target={'id':group_id,'name':group['name']}
        self.dm_target=None
        self.header_label.config(text=f'👥 {group["name"]}')
        self.group_badge.pack(side='left',padx=4)
        self.dm_badge.pack_forget()
        self._append_system(f'Now in group: {group["name"]} ({", ".join(group["members"])})')

    def _show_group_members_bar(self,group):
        # Remove existing members bar if any
        if hasattr(self,'_members_bar') and self._members_bar:
            try: self._members_bar.destroy()
            except Exception: pass
        members=group.get('members',[])
        creator=group.get('creator','')
        bar=tk.Frame(self,bg=C['group_bg'])
        self._members_bar=bar
        tk.Label(bar,text=f'👥 Group Members ({len(members)}):',
                 font=FONT_SMALL,bg=C['group_bg'],fg=C['accent2'],
                 padx=10,pady=4).pack(side='left')
        for m in sorted(members):
            color=C['accent'] if m==creator else C['online']
            suffix=' 👑' if m==creator else ''
            tk.Label(bar,text=f'{m}{suffix}',font=FONT_SMALL,
                     bg=C['group_bg'],fg=color,padx=6,pady=4).pack(side='left')
        tk.Button(bar,text='✕',font=FONT_SMALL,bg=C['group_bg'],
                  fg=C['text_dim'],relief='flat',bd=0,padx=8,cursor='hand2',
                  command=lambda:bar.pack_forget()).pack(side='right',padx=4)
        # Pack after header
        bar.pack(fill='x',after=self.header)

    # ── Create Group ───────────────────────────────────────────────────
    def _create_group_dialog(self):
        if not self.client or not self.client.connected:
            messagebox.showwarning('Not Connected','Connect first.',parent=self); return
        dlg=CreateGroupDialog(self,self.users,self.username)
        self.wait_window(dlg)
        if dlg.result and self.client:
            self.client.create_group(dlg.result['name'],dlg.result['members'])

    # ── Pin ────────────────────────────────────────────────────────────
    def _update_pin_bar(self):
        if self.pinned:
            latest=self.pinned[0]
            short=latest['text'][:60]+('…' if len(latest['text'])>60 else '')
            self.pin_label.config(text=f'📌  {short}  — {latest["by"]}')
            self.pin_frame.pack(fill='x',after=self.header)
        else:
            self.pin_frame.pack_forget()

    def _pin_current(self):
        text=self.input_var.get().strip()
        if not text:
            text=simpledialog.askstring('Pin Message','Enter message to pin:',parent=self)
        if text and self.client:
            self.client.pin_message(text); self.input_var.set('')

    def _show_pins(self):
        if not self.pinned:
            messagebox.showinfo('Pinned','No pinned messages.',parent=self); return
        win=tk.Toplevel(self); win.title('📌 Pinned')
        win.configure(bg=C['bg']); win.geometry('420x300'); win.transient(self)
        tk.Label(win,text='📌 Pinned Messages',font=FONT_BOLD,bg=C['bg'],fg=C['accent']).pack(pady=12)
        for i,p in enumerate(self.pinned):
            f=tk.Frame(win,bg=C['pin_bg']); f.pack(fill='x',padx=16,pady=3)
            tk.Label(f,text=p['text'],font=FONT_MAIN,bg=C['pin_bg'],fg=C['text'],
                     wraplength=300,anchor='w').pack(side='left',padx=8,pady=6)
            tk.Button(f,text='✕',font=FONT_SMALL,bg=C['pin_bg'],fg=C['text_dim'],
                      relief='flat',bd=0,cursor='hand2',
                      command=lambda idx=i,w=win:self._unpin(idx,w)).pack(side='right',padx=4)

    def _unpin(self,index,win):
        if self.client: self.client.unpin_message(index)
        win.destroy()

    # ── Search ─────────────────────────────────────────────────────────
    def _toggle_search(self):
        self._search_visible=not self._search_visible
        if self._search_visible:
            self.search_frame.pack(fill='x',before=self.chat_text.master)
            self.search_entry.focus_set()
        else:
            self.search_frame.pack_forget()
            self._clear_search_highlights(); self.search_var.set('')

    def _do_search(self,*_):
        self._clear_search_highlights()
        q=self.search_var.get().strip()
        if not q: self.search_count.config(text=''); return
        count=0; start='1.0'
        while True:
            pos=self.chat_text.search(q,start,stopindex='end',nocase=True)
            if not pos: break
            end_pos=f'{pos}+{len(q)}c'
            self.chat_text.tag_add('search_hl',pos,end_pos)
            self._search_highlights.append((pos,end_pos))
            start=end_pos; count+=1
        self.search_count.config(text=f'{count} result{"s" if count!=1 else ""}')
        if self._search_highlights: self.chat_text.see(self._search_highlights[0][0])

    def _clear_search_highlights(self):
        self.chat_text.tag_remove('search_hl','1.0','end')
        self._search_highlights.clear()

    # ── Right-click ────────────────────────────────────────────────────
    def _on_right_click(self,event):
        menu=tk.Menu(self,tearoff=0,bg=C['panel'],fg=C['text'],
                     activebackground=C['accent'],activeforeground='white',relief='flat',bd=0)
        menu.add_command(label='📋 Copy',command=lambda:self.event_generate('<<Copy>>'))
        menu.add_command(label='🔍 Search',command=self._toggle_search)
        menu.add_command(label='📌 Pin selected',command=self._pin_selected)
        try: menu.tk_popup(event.x_root,event.y_root)
        finally: menu.grab_release()

    def _pin_selected(self):
        try:
            text=self.chat_text.get('sel.first','sel.last').strip()
            if text and self.client: self.client.pin_message(text)
        except tk.TclError: pass

    # ── Stats ──────────────────────────────────────────────────────────
    def _show_stats(self):
        if self.client: self.client.request_stats()

    # ── Reply ──────────────────────────────────────────────────────────
    def _set_reply(self,msg_id,sender,text):
        self.reply_target={'id':msg_id,'from':sender,'text':text}
        short=text[:50]+('…' if len(text)>50 else '')
        self.reply_label.config(text=f'↩️ Replying to {sender}: {short}')
        self.reply_frame.pack(fill='x',before=self.typing_label)
        self.input_entry.focus_set()

    def _cancel_reply(self):
        self.reply_target=None; self.reply_frame.pack_forget()

    # ── History ────────────────────────────────────────────────────────
    def _append_history(self,line):
        self.history.append(line)
        try:
            with open(self.history_file,'a',encoding='utf-8') as f: f.write(line+'\n')
        except Exception: pass

    def _manual_save(self):
        if not self.history:
            messagebox.showinfo('Save','No messages to save yet.',parent=self); return
        path=filedialog.asksaveasfilename(
            defaultextension='.txt',filetypes=[('Text files','*.txt'),('All files','*.*')],
            initialfile=f'lanchat_{self.username}_{datetime.now().strftime("%Y%m%d")}.txt',
            title='Save Chat History')
        if path:
            try:
                with open(path,'w',encoding='utf-8') as f: f.write('\n'.join(self.history))
                messagebox.showinfo('Saved',f'Saved to:\n{path}',parent=self)
            except Exception as e: messagebox.showerror('Error',str(e),parent=self)

    # ── Chat display ───────────────────────────────────────────────────
    def _append(self,fn):
        self.chat_text.config(state='normal'); fn()
        self.chat_text.config(state='disabled'); self.chat_text.see('end')

    def _append_system(self,text):
        self._append(lambda:self.chat_text.insert('end',f'  {text}\n','system'))
        self._append_history(f'[SYSTEM] {text}')

    def _append_message(self,msg,private=False,group_name=None,is_admin=False):
        msg_id=msg.get('id','')
        sender=msg.get('from','')
        time_str=msg.get('time','')
        encrypted=msg.get('encrypted',False)
        reply_preview=msg.get('reply_preview')
        deleted=msg.get('deleted',False)
        edited=msg.get('edited',False)
        text=msg.get('text','')

        display_text=text; was_decrypted=False
        if encrypted and self.enc_key and HAS_CRYPTO:
            try: display_text=decrypt(text,self.enc_key); was_decrypted=True
            except Exception: display_text='[🔐 Encrypted — wrong passphrase]'

        def _do():
            if is_admin and private:
                tag='admin_dm'
            elif is_admin:
                tag='admin_msg'
            elif group_name:
                tag='group_msg'
            elif private:
                tag='private'
            else:
                tag='me' if sender==self.username else 'them'

            # Reply quote
            if reply_preview:
                self.chat_text.insert('end',
                    f'  ↩️  {reply_preview["from"]}: {reply_preview["text"][:50]}\n','reply_quote')

            # Main line
            prefix='🔒 ' if private else (f'👥 [{group_name}] ' if group_name else '')
            self.chat_text.insert('end',f'  {time_str}  ','time')
            self.chat_text.insert('end',f'{prefix}{sender}',tag)
            if was_decrypted: self.chat_text.insert('end',' 🔐','enc_tag')
            if edited: self.chat_text.insert('end',' (edited)','edited_tag')

            msg_tag=f'msgtext_{msg_id}'
            self.chat_text.tag_config(msg_tag,foreground=C['text_dim'] if deleted else C['text'])
            self.chat_text.insert('end',f':  {display_text}\n',msg_tag)

            # Reaction + action row
            if msg_id and not is_admin:
                self.chat_text.insert('end','  ','time')
                for emoji in QUICK_REACTIONS:
                    rtag=f'qr_{msg_id}_{emoji}'
                    self.chat_text.tag_config(rtag,foreground=C['text_dim'],font=('Segoe UI',12))
                    self.chat_text.tag_bind(rtag,'<Button-1>',
                                           lambda e,mid=msg_id,em=emoji:self._send_react(mid,em))
                    self.chat_text.tag_bind(rtag,'<Enter>',lambda e:self.chat_text.config(cursor='hand2'))
                    self.chat_text.tag_bind(rtag,'<Leave>',lambda e:self.chat_text.config(cursor='arrow'))
                    self.chat_text.insert('end',f'{emoji} ',rtag)

                if sender==self.username:
                    edit_tag=f'edit_{msg_id}'; del_tag=f'del_{msg_id}'
                    self.chat_text.tag_config(edit_tag,foreground=C['text_dim'],font=('Segoe UI',9),underline=True)
                    self.chat_text.tag_config(del_tag,foreground='#f87171',font=('Segoe UI',9),underline=True)
                    self.chat_text.tag_bind(edit_tag,'<Button-1>',
                                           lambda e,mid=msg_id,t=display_text:self._edit_msg(mid,t))
                    self.chat_text.tag_bind(del_tag,'<Button-1>',
                                           lambda e,mid=msg_id:self._delete_msg(mid))
                    self.chat_text.tag_bind(edit_tag,'<Enter>',lambda e:self.chat_text.config(cursor='hand2'))
                    self.chat_text.tag_bind(edit_tag,'<Leave>',lambda e:self.chat_text.config(cursor='arrow'))
                    self.chat_text.tag_bind(del_tag,'<Enter>',lambda e:self.chat_text.config(cursor='hand2'))
                    self.chat_text.tag_bind(del_tag,'<Leave>',lambda e:self.chat_text.config(cursor='arrow'))
                    self.chat_text.insert('end','  ✏️ edit',edit_tag)
                    self.chat_text.insert('end','  🗑️ delete',del_tag)

                reply_tag=f'reply_{msg_id}'
                self.chat_text.tag_config(reply_tag,foreground=C['accent2'],font=('Segoe UI',9),underline=True)
                self.chat_text.tag_bind(reply_tag,'<Button-1>',
                                       lambda e,mid=msg_id,s=sender,t=display_text:self._set_reply(mid,s,t))
                self.chat_text.tag_bind(reply_tag,'<Enter>',lambda e:self.chat_text.config(cursor='hand2'))
                self.chat_text.tag_bind(reply_tag,'<Leave>',lambda e:self.chat_text.config(cursor='arrow'))
                self.chat_text.insert('end','  ↩️ reply',reply_tag)

                if sender==self.username:
                    rr_tag=f'rr_{msg_id}'
                    self.chat_text.tag_config(rr_tag,foreground=C['text_dim'],font=('Segoe UI',8))
                    self.chat_text.insert('end','  ✓',rr_tag)

                self.chat_text.insert('end','\n')
                react_line_tag=f'reactline_{msg_id}'
                self.chat_text.tag_config(react_line_tag)
                self.chat_text.insert('end','\n',react_line_tag)
                self.msg_widgets[msg_id]={'react_line_tag':react_line_tag,'reactions':{}}
            else:
                self.chat_text.insert('end','\n')

        self._append(_do)
        label='PRIVATE' if private else (f'GROUP[{group_name}]' if group_name else 'MSG')
        self._append_history(f'[{time_str}] [{label}] {sender}: {display_text}')

        if msg_id and sender!=self.username and self.client and not is_admin:
            self.after(500,lambda:self.client and self.client.mark_read(msg_id))

    def _append_file_msg(self,sender,filename,filesize,time_str,filedata,private=False):
        size_str=f'{filesize:,} B' if filesize<1024 else f'{filesize//1024} KB'
        def _do():
            tag='me' if sender==self.username else 'file_msg'
            self.chat_text.insert('end',f'  {time_str}  ','time')
            self.chat_text.insert('end',f'{sender}',tag)
            self.chat_text.insert('end',f':  📎 {filename} ({size_str})  ','msg_text')
            dl_tag=f'dl_{id(filedata)}'
            self.chat_text.tag_config(dl_tag,foreground='#34d399',underline=True,font=FONT_SMALL)
            self.chat_text.tag_bind(dl_tag,'<Button-1>',
                                   lambda e,d=filedata,n=filename:self._save_file(d,n))
            self.chat_text.tag_bind(dl_tag,'<Enter>',lambda e:self.chat_text.config(cursor='hand2'))
            self.chat_text.tag_bind(dl_tag,'<Leave>',lambda e:self.chat_text.config(cursor='arrow'))
            self.chat_text.insert('end','[Download]',dl_tag)
            self.chat_text.insert('end','\n')
        self._append(_do)
        self._append_history(f'[{time_str}] [FILE] {sender}: {filename}')

    def _save_file(self,b64data,filename):
        path=filedialog.asksaveasfilename(initialfile=filename,title='Save File')
        if path:
            try:
                with open(path,'wb') as f: f.write(base64.b64decode(b64data))
                messagebox.showinfo('Saved',f'Saved:\n{path}',parent=self)
            except Exception as e: messagebox.showerror('Error',str(e),parent=self)

    # ── Edit/Delete ────────────────────────────────────────────────────
    def _edit_msg(self,msg_id,current_text):
        new_text=simpledialog.askstring('Edit','Edit your message:',
                                        initialvalue=current_text,parent=self)
        if new_text and new_text.strip() and self.client:
            self.client.edit_message(msg_id,new_text.strip())

    def _delete_msg(self,msg_id):
        if messagebox.askyesno('Delete','Delete this message?',parent=self):
            if self.client: self.client.delete_message(msg_id)

    def _apply_edit(self,msg_id,new_text):
        tag=f'msgtext_{msg_id}'
        try:
            self.chat_text.config(state='normal')
            start=self.chat_text.tag_ranges(tag)
            if start:
                self.chat_text.delete(start[0],start[1])
                self.chat_text.insert(start[0],f':  {new_text}\n',tag)
            self.chat_text.config(state='disabled')
        except Exception: pass

    def _apply_delete(self,msg_id):
        tag=f'msgtext_{msg_id}'
        try:
            self.chat_text.config(state='normal')
            start=self.chat_text.tag_ranges(tag)
            if start:
                self.chat_text.delete(start[0],start[1])
                self.chat_text.insert(start[0],':  [Message deleted]\n','deleted')
            self.chat_text.config(state='disabled')
        except Exception: pass

    # ── Reactions ──────────────────────────────────────────────────────
    def _send_react(self,msg_id,emoji):
        if self.client: self.client.react(msg_id,emoji)

    def _update_reactions(self,msg_id,reactions):
        if msg_id not in self.msg_widgets: return
        react_line_tag=self.msg_widgets[msg_id]['react_line_tag']
        try:
            self.chat_text.config(state='normal')
            ranges=self.chat_text.tag_ranges(react_line_tag)
            if not ranges: return
            if reactions:
                parts=[]
                for em,users in reactions.items():
                    me_reacted=self.username in users
                    parts.append(f'{"[" if me_reacted else ""}{em} {len(users)}{"]" if me_reacted else ""}')
                react_str='  '+'  '.join(parts)+'\n'
            else:
                react_str='\n'
            existing=self.chat_text.get(ranges[0],ranges[1])
            if existing: self.chat_text.delete(ranges[0],ranges[1])
            self.chat_text.insert(ranges[0],react_str,react_line_tag)
            self.chat_text.config(state='disabled')
        except Exception: pass

    def _update_read_receipt(self,msg_id,read_by):
        rr_tag=f'rr_{msg_id}'
        try:
            self.chat_text.config(state='normal')
            ranges=self.chat_text.tag_ranges(rr_tag)
            if ranges:
                self.chat_text.delete(ranges[0],ranges[1])
                readers=[r for r in read_by if r!=self.username]
                if readers:
                    self.chat_text.tag_config(rr_tag,foreground=C['online'],font=('Segoe UI',8))
                    self.chat_text.insert(ranges[0],f'  ✓✓ Seen by {", ".join(readers[:3])}',rr_tag)
            self.chat_text.config(state='disabled')
        except Exception: pass

    # ── Typing ─────────────────────────────────────────────────────────
    def _update_typing(self):
        typers=self._typers-{self.username}
        if not typers: self.typing_label.config(text='')
        elif len(typers)==1: self.typing_label.config(text=f'  ✍️  {next(iter(typers))} is typing…')
        else: self.typing_label.config(text=f'  ✍️  {", ".join(list(typers)[:3])} are typing…')

    def _stop_typing(self):
        if self._is_typing_sent and self.client:
            self.client.send_typing(False); self._is_typing_sent=False

    def _clear_typer(self,sender):
        self._typers.discard(sender); self._update_typing()

    # ── Network ────────────────────────────────────────────────────────
    def _on_server_message(self,msg):
        self.after(0,lambda:self._handle(msg))

    def _handle(self,msg):
        kind=msg.get('type')

        if kind in ('welcome','system'):
            self._append_system(msg.get('text',''))
            users_list=msg.get('users',[])
            if users_list is not None:
                self.users=[u['username'] for u in users_list]
                self.users_meta={u['username']:u for u in users_list}
                self._refresh_user_list()
            if kind=='welcome':
                self.pinned=msg.get('pinned',[]); self._update_pin_bar()
                if self.enc_key: self.enc_badge.pack(side='left',padx=4)
                for m in msg.get('recent_messages',[]): self._append_message(m)
                # Load my groups
                for g in msg.get('groups',[]):
                    self.my_groups[g['id']]=g
                self._refresh_groups_sidebar()

        elif kind=='message':
            is_admin=msg.get('is_admin',False)
            self._append_message(msg,is_admin=is_admin)
            if msg['from']!=self.username and self.sound_enabled:
                threading.Thread(target=play_notification,daemon=True).start()
            self._typers.discard(msg['from']); self._update_typing()

        elif kind=='private':
            self._append_message(msg,private=True)
            if msg['from']!=self.username and self.sound_enabled:
                threading.Thread(target=play_notification,daemon=True).start()

        elif kind=='group_message':
            gname=msg.get('group_name','Group')
            self._append_message(msg,group_name=gname)
            if msg['from']!=self.username and self.sound_enabled:
                threading.Thread(target=play_notification,daemon=True).start()

        elif kind=='group_created':
            group_id=msg.get('group_id')
            gname=msg.get('group_name','Group')
            creator=msg.get('creator','')
            members=msg.get('members',[])
            self.my_groups[group_id]={'id':group_id,'name':gname,
                                      'creator':creator,'members':members}
            self._refresh_groups_sidebar()
            self._append_system(f'👥 New group created: "{gname}" by {creator} '
                                 f'(members: {", ".join(members)})')
            if self.sound_enabled:
                threading.Thread(target=play_notification,daemon=True).start()

        elif kind=='file':
            self._append_file_msg(msg['from'],msg.get('filename','file'),
                                  msg.get('filesize',0),msg.get('time',''),
                                  msg.get('filedata',''),'to' in msg)
            if msg['from']!=self.username and self.sound_enabled:
                threading.Thread(target=play_notification,daemon=True).start()

        elif kind=='typing':
            sender=msg.get('from','')
            if msg.get('is_typing'):
                self._typers.add(sender)
                if sender in self._typer_clears: self.after_cancel(self._typer_clears[sender])
                self._typer_clears[sender]=self.after(3000,lambda s=sender:self._clear_typer(s))
            else:
                self._typers.discard(sender)
            self._update_typing()

        elif kind=='edit':
            self._apply_edit(msg['msg_id'],msg['text'])

        elif kind=='delete':
            self._apply_delete(msg['msg_id'])

        elif kind=='react_update':
            self._update_reactions(msg['msg_id'],msg['reactions'])

        elif kind=='read_receipt':
            self._update_read_receipt(msg['msg_id'],msg['read_by'])

        elif kind=='pin_update':
            self.pinned=msg.get('pinned',[]); self._update_pin_bar()
            self._append_system(f'{msg.get("by","Someone")} updated pinned messages.')

        elif kind=='stats':
            self._last_stats=msg.get('data',{}); self._last_users_stat=msg.get('users',[])
            self._show_stats_window()

        elif kind=='error':
            messagebox.showerror('Error',msg.get('text',''))
            self.client=None; self.withdraw(); self._show_login()

    def _show_stats_window(self):
        win=tk.Toplevel(self); win.title('📊 Stats')
        win.configure(bg=C['bg']); win.geometry('500x420'); win.transient(self)
        stats=self._last_stats; users=self._last_users_stat
        tk.Label(win,text='📊 Chat Statistics',font=FONT_BOLD,
                 bg=C['bg'],fg=C['accent']).pack(pady=(16,8))
        row1=tk.Frame(win,bg=C['bg']); row1.pack(fill='x',padx=16,pady=(0,4))
        row2=tk.Frame(win,bg=C['bg']); row2.pack(fill='x',padx=16,pady=(0,8))
        def card(parent,lbl,val,col):
            f=tk.Frame(parent,bg=C['panel'],pady=12,padx=10)
            f.pack(side='left',expand=True,fill='x',padx=4)
            tk.Label(f,text=val,font=('Segoe UI',15,'bold'),bg=C['panel'],fg=col,anchor='center').pack(fill='x')
            tk.Label(f,text=lbl,font=FONT_SMALL,bg=C['panel'],fg=C['text_dim'],anchor='center').pack(fill='x')
        card(row1,'Total Messages',str(stats.get('total_messages',0)),C['accent'])
        card(row1,'Online Now',str(stats.get('online_now',0)),C['accent2'])
        card(row2,'Uptime',stats.get('uptime','--'),C['online'])
        card(row2,'Peak Hour',f'{stats.get("peak_hour",0):02d}:00','#f472b6')
        tk.Label(win,text='Top Chatters',font=FONT_BOLD,bg=C['bg'],fg=C['text']).pack(pady=(8,4))
        lbf=tk.Frame(win,bg=C['panel']); lbf.pack(fill='x',padx=16,pady=(0,16))
        for i,u in enumerate(sorted(users,key=lambda x:x.get('msg_count',0),reverse=True)[:5]):
            row=tk.Frame(lbf,bg=C['panel']); row.pack(fill='x',padx=10,pady=2)
            medal=['🥇','🥈','🥉','4️⃣','5️⃣'][i]
            tk.Label(row,text=f'{medal}  {u["username"]}',font=FONT_MAIN,bg=C['panel'],fg=C['text']).pack(side='left')
            tk.Label(row,text=f'{u.get("msg_count",0)} msgs',font=FONT_SMALL,bg=C['panel'],fg=C['text_dim']).pack(side='right')

    def _on_disconnect(self):
        self.after(0,lambda:messagebox.showerror('Disconnected','Lost connection to server.'))

    # ── Sending ────────────────────────────────────────────────────────
    def _send_message(self,event=None):
        if not self.client or not self.client.connected: return
        text=self.input_var.get().strip()
        if not text: return
        encrypted=False; send_text=text
        if self.enc_key and HAS_CRYPTO:
            send_text=encrypt(text,self.enc_key); encrypted=True
        reply_id=self.reply_target['id'] if self.reply_target else None

        if self.group_target:
            # Send to group
            self.client.send_group_message(self.group_target['id'],send_text,encrypted)
        elif self.dm_target:
            self.client.send_private(self.dm_target,send_text,encrypted,reply_id)
        else:
            self.client.send_message(send_text,encrypted,reply_id)

        self.suggestion_engine.feed(text)
        self.input_var.set(''); self._clear_suggestions()
        self._stop_typing(); self._cancel_reply()

    def _send_file(self):
        if not self.client or not self.client.connected:
            messagebox.showwarning('Not Connected','Connect first.',parent=self); return
        path=filedialog.askopenfilename(title='Select File')
        if not path: return
        if os.path.getsize(path)>10*1024*1024:
            messagebox.showerror('Too Large','Max 10 MB.',parent=self); return
        try: self.client.send_file(path,self.dm_target)
        except Exception as e: messagebox.showerror('Error',str(e),parent=self)

    def _open_emoji(self):
        EmojiPicker(self,lambda e:(
            self.input_var.set(self.input_var.get()+e),
            self.input_entry.icursor('end'),
            self.input_entry.focus_set()
        ))

    # ── Suggestions ────────────────────────────────────────────────────
    def _on_input_change(self,*_):
        text=self.input_var.get()
        if text and self.client and self.client.connected:
            if not self._is_typing_sent:
                self.client.send_typing(True); self._is_typing_sent=True
            if self._typing_job: self.after_cancel(self._typing_job)
            self._typing_job=self.after(2000,self._stop_typing)
        elif not text: self._stop_typing()
        if self._suggest_job: self.after_cancel(self._suggest_job)
        self._suggest_job=self.after(120,self._update_suggestions)

    def _update_suggestions(self):
        text=self.input_var.get(); suggs=self.suggestion_engine.suggest(text,n=5)
        self._clear_suggestions()
        for s in suggs:
            short=s if len(s)<=48 else s[:45]+'…'
            btn=tk.Button(self.suggest_frame,text=short,font=FONT_SMALL,
                          bg=C['suggest_bg'],fg=C['text_dim'],relief='flat',bd=0,
                          padx=10,pady=4,cursor='hand2',
                          activebackground=C['suggest_hl'],activeforeground='white',
                          command=lambda v=s:self._apply_suggestion(v))
            btn.pack(side='left',padx=2,pady=4); self.suggest_buttons.append(btn)

    def _clear_suggestions(self):
        for b in self.suggest_buttons: b.destroy()
        self.suggest_buttons.clear()

    def _apply_suggestion(self,text):
        self.input_var.set(text); self.input_entry.icursor('end'); self.input_entry.focus_set()

    def _tab_complete(self,event=None):
        if self.suggest_buttons:
            first=self.suggest_buttons[0].cget('text')
            if not first.endswith('…'): self._apply_suggestion(first)
        return 'break'

    def _on_close(self):
        if self.client: self.client.disconnect()
        if self.history:
            self._append_history(f'=== Session ended {datetime.now().strftime("%Y-%m-%d %H:%M")} ===')
        self.destroy()


if __name__ == '__main__':
    app=ChatApp()
    app.mainloop()
