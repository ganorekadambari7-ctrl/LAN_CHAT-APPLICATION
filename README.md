# 🌐 LAN Chat v5 Upgraded

## 🆕 3 New Features

### 1. 🔐 Admin Login Panel
- Running `python server.py` now shows a **Login Screen** first
- Admin must enter username + password to access the panel
- Default credentials: **admin / admin123**
- Admin can also enter an **Encryption Passphrase** to read encrypted messages

### 2. 💬 Admin Direct Message (DM) to Users
- In the Admin Panel, click **💬** next to any user to select them as DM target
- Selected user is highlighted in blue
- Type in the DM box → click **Send DM 💬**
- Message is delivered privately to that user only
- Shows as 📢 ADMIN private message on client side
- All admin DMs are logged in the **DM Monitor** tab

### 3. 👥 Group Member Visibility
- When you open a group, a **member bar** appears showing:
  - All member names
  - 👑 Crown on the group creator
  - Member count in the header
- Group info also printed in chat: Members, Creator
- Members bar can be dismissed with ✕

---

## 🚀 How to Run

```bash
pip install cryptography

python server.py    # Shows login → enter admin / admin123
python client.py    # Client on every device
```

## 📁 Files
```
lan_chat_v5u/
├── server.py         ← Admin Panel with Login + DM
├── client.py         ← Client with Group Member Visibility
├── crypto_utils.py   ← AES encryption
└── README.md
```

## 🔐 Encryption at Server
- Enter the same passphrase used by clients in the admin login screen
- Server will decrypt and display messages in plaintext in the monitor
- Admin DMs can also be sent encrypted
