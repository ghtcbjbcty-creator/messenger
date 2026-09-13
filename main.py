import socket
import json
import threading
import time
import queue

from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.button import Button
from kivy.uix.popup import Popup
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.uix.screenmanager import ScreenManager, Screen
from kivy.properties import StringProperty

HOST_IP = "192.168.0.219"
HOST_PORT = 5555

# =========================================================
# СЕТЬ
# =========================================================
class NetClient:
    def __init__(self):
        self.sock = None
        self.queue = queue.Queue()
        self.connected = False

    def connect(self, ip=None, port=None):
        try:
            if self.sock:
                self.sock.close()
        except:
            pass
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.settimeout(10)
        self.sock.connect((ip or HOST_IP, port or HOST_PORT))
        self.sock.setblocking(False)
        self.queue = queue.Queue()
        self.connected = True
        threading.Thread(target=self._receive, daemon=True).start()

    def send(self, pkt):
        try:
            self.sock.sendall((json.dumps(pkt) + "\n").encode("utf-8"))
            return True
        except:
            self.connected = False
            return False

    def _receive(self):
        buffer = ""
        while self.connected:
            try:
                data = self.sock.recv(4096)
                if not data:
                    self.queue.put(None)
                    self.connected = False
                    break
                buffer += data.decode("utf-8", errors="ignore")
                lines = buffer.split("\n")
                buffer = lines[-1]
                for line in lines[:-1]:
                    if line.strip():
                        try:
                            self.queue.put(json.loads(line))
                        except:
                            pass
            except BlockingIOError:
                time.sleep(0.01)
            except:
                self.queue.put(None)
                self.connected = False
                break

    def get_packet(self):
        try:
            return self.queue.get_nowait()
        except queue.Empty:
            return "EMPTY"

net = NetClient()

# =========================================================
# ЭКРАН АВТОРИЗАЦИИ
# =========================================================
class AuthScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.mode = "login"
        self.waiting = False
        self.start_time = 0

        layout = BoxLayout(orientation="vertical", padding=30, spacing=10)

        self.title = Label(text="Вход", font_size=28, size_hint_y=0.15)
        layout.add_widget(self.title)

        self.toggle_btn = Button(text="Регистрация", size_hint_y=0.1)
        self.toggle_btn.bind(on_press=self.toggle_mode)
        layout.add_widget(self.toggle_btn)

        self.username_input = TextInput(hint_text="Логин", multiline=False, size_hint_y=0.1)
        layout.add_widget(self.username_input)

        self.password_input = TextInput(hint_text="Пароль", multiline=False, password=True, size_hint_y=0.1)
        layout.add_widget(self.password_input)

        self.submit_btn = Button(text="Войти", size_hint_y=0.12,
                                  background_color=(0.2, 0.6, 0.2, 1))
        self.submit_btn.bind(on_press=self.submit)
        layout.add_widget(self.submit_btn)

        self.status_label = Label(text="", font_size=14, size_hint_y=0.1,
                                   color=(1, 0.3, 0.3, 1))
        layout.add_widget(self.status_label)

        layout.add_widget(Label(text="", size_hint_y=0.33))
        self.add_widget(layout)

        Clock.schedule_interval(self.check_timeout, 0.5)

    def toggle_mode(self, *args):
        if self.mode == "login":
            self.mode = "register"
            self.title.text = "Регистрация"
            self.toggle_btn.text = "Вход"
            self.submit_btn.text = "Создать"
        else:
            self.mode = "login"
            self.title.text = "Вход"
            self.toggle_btn.text = "Регистрация"
            self.submit_btn.text = "Войти"
        self.status_label.text = ""
        self.waiting = False
        self.submit_btn.disabled = False

    def submit(self, *args):
        if self.waiting:
            return
        u = self.username_input.text.strip()
        p = self.password_input.text.strip()
        if not u or not p:
            self.status_label.text = "Заполните все поля"
            return
        self.status_label.text = "Ожидание..."
        self.submit_btn.disabled = True
        self.waiting = True
        self.start_time = time.time()
        if not net.send({"action": self.mode, "username": u, "password": p}):
            self.status_label.text = "Не удалось отправить"
            self.submit_btn.disabled = False
            self.waiting = False
            self.try_reconnect()

    def try_reconnect(self):
        try:
            net.connect()
            self.status_label.text = "Переподключено. Попробуйте снова."
        except:
            self.status_label.text = "Сервер недоступен"

    def check_timeout(self, dt):
        if self.waiting and (time.time() - self.start_time > 10):
            self.waiting = False
            self.submit_btn.disabled = False
            self.status_label.text = "Сервер не ответил. Попробуйте снова."

    def on_auth_ok(self, username):
        self.waiting = False
        self.submit_btn.disabled = False
        app = App.get_running_app()
        app.username = username
        app.sm.current = "main"

    def on_auth_error(self, text):
        self.waiting = False
        self.submit_btn.disabled = False
        self.status_label.text = text
        self.try_reconnect()

    def on_banned(self, text):
        self.waiting = False
        self.submit_btn.disabled = False
        self.status_label.text = text
        self.try_reconnect()

# =========================================================
# ЭКРАН СПИСКА
# =========================================================
class MainScreen(Screen):
    current_tab = StringProperty("contacts")

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.build_ui()

    def build_ui(self):
        root = BoxLayout(orientation="vertical")

        header = BoxLayout(size_hint_y=0.08)
        self.btn_contacts = Button(text="Чаты", size_hint_x=0.33)
        self.btn_contacts.bind(on_press=lambda x: self.switch_tab("contacts"))
        self.btn_groups = Button(text="Группы", size_hint_x=0.33)
        self.btn_groups.bind(on_press=lambda x: self.switch_tab("groups"))
        self.btn_channels = Button(text="Каналы", size_hint_x=0.33)
        self.btn_channels.bind(on_press=lambda x: self.switch_tab("channels"))
        header.add_widget(self.btn_contacts)
        header.add_widget(self.btn_groups)
        header.add_widget(self.btn_channels)
        root.add_widget(header)

        self.scroll = ScrollView(size_hint_y=0.72)
        self.list_container = BoxLayout(orientation="vertical", size_hint_y=None, spacing=2)
        self.list_container.bind(minimum_height=self.list_container.setter("height"))
        self.scroll.add_widget(self.list_container)
        root.add_widget(self.scroll)

        bottom = BoxLayout(size_hint_y=0.12, spacing=5, padding=5)
        self.text_input = TextInput(hint_text="Имя", multiline=False, size_hint_x=0.5)
        bottom.add_widget(self.text_input)

        self.add_btn = Button(text="Добавить", size_hint_x=0.25,
                               background_color=(0.2, 0.4, 0.7, 1))
        self.add_btn.bind(on_press=self.do_add)
        bottom.add_widget(self.add_btn)

        self.create_btn = Button(text="Создать", size_hint_x=0.25,
                                  background_color=(0.2, 0.6, 0.3, 1))
        self.create_btn.bind(on_press=self.do_create)
        bottom.add_widget(self.create_btn)
        root.add_widget(bottom)

        self.status_label = Label(text="", font_size=12, size_hint_y=0.04,
                                   color=(0.8, 0.8, 0.3, 1))
        root.add_widget(self.status_label)

        logout_btn = Button(text="Выйти", size_hint_y=0.04,
                             background_color=(0.6, 0.2, 0.2, 1))
        logout_btn.bind(on_press=lambda x: App.get_running_app().stop())
        root.add_widget(logout_btn)

        self.add_widget(root)

    def switch_tab(self, tab):
        self.current_tab = tab
        self.text_input.text = ""
        if tab == "contacts":
            self.btn_contacts.background_color = (0.2, 0.4, 0.8, 1)
            self.btn_groups.background_color = (0.3, 0.3, 0.3, 1)
            self.btn_channels.background_color = (0.3, 0.3, 0.3, 1)
            self.create_btn.disabled = True
            self.create_btn.opacity = 0.3
        elif tab == "groups":
            self.btn_contacts.background_color = (0.3, 0.3, 0.3, 1)
            self.btn_groups.background_color = (0.2, 0.4, 0.8, 1)
            self.btn_channels.background_color = (0.3, 0.3, 0.3, 1)
            self.create_btn.disabled = False
            self.create_btn.opacity = 1
        elif tab == "channels":
            self.btn_contacts.background_color = (0.3, 0.3, 0.3, 1)
            self.btn_groups.background_color = (0.3, 0.3, 0.3, 1)
            self.btn_channels.background_color = (0.2, 0.4, 0.8, 1)
            self.create_btn.disabled = False
            self.create_btn.opacity = 1
        self.refresh_list()

    def refresh_list(self):
        self.list_container.clear_widgets()
        app = App.get_running_app()

        if self.current_tab == "contacts":
            for req in app.pending_in:
                row = BoxLayout(size_hint_y=None, height=50, spacing=5)
                row.add_widget(Label(text=req, size_hint_x=0.5, halign="left"))
                acc = Button(text="+", size_hint_x=0.25, background_color=(0.2, 0.7, 0.2, 1))
                acc.bind(on_press=lambda x, r=req: self.accept_contact(r))
                row.add_widget(acc)
                dec = Button(text="X", size_hint_x=0.25, background_color=(0.7, 0.2, 0.2, 1))
                dec.bind(on_press=lambda x, r=req: self.decline_contact(r))
                row.add_widget(dec)
                self.list_container.add_widget(row)

            for req in app.pending_out:
                self.list_container.add_widget(
                    Label(text=f"{req} (ожидает)", size_hint_y=None, height=40,
                          color=(0.5, 0.5, 0.5, 1), halign="left"))

            if not app.contacts:
                self.list_container.add_widget(
                    Label(text="Нет контактов. Введите ник + Добавить",
                          size_hint_y=None, height=40, color=(0.5, 0.5, 0.5, 1)))

            for c in app.contacts:
                name = c["name"]
                online = c.get("online", False)
                badge = app.unread.get(name, 0)
                color = (0.3, 0.9, 0.3, 1) if online else (0.8, 0.8, 0.8, 1)
                lbl_text = name + ("  ●" if online else "")
                if badge > 0:
                    lbl_text += f"  ({badge})"
                row = Button(text=lbl_text, size_hint_y=None, height=50,
                             color=color, halign="left")
                row.bind(on_press=lambda x, n=name: self.open_chat(n))
                self.list_container.add_widget(row)

        elif self.current_tab == "groups":
            # Заявки на вступление (видит только админ)
            for gname, reqs in app.group_join_requests.items():
                if not reqs:
                    continue
                self.list_container.add_widget(
                    Label(text=f"Заявки в группу: {gname} ({len(reqs)})",
                          size_hint_y=None, height=35, color=(1, 0.7, 0.2, 1),
                          font_size=14, bold=True, halign="left"))
                for req_user in reqs:
                    row = BoxLayout(size_hint_y=None, height=50, spacing=5)
                    row.add_widget(Label(text=f"{req_user} -> {gname}",
                                         size_hint_x=0.5, halign="left",
                                         color=(1, 0.7, 0.2, 1)))
                    acc = Button(text="+", size_hint_x=0.25,
                                 background_color=(0.2, 0.7, 0.2, 1))
                    acc.bind(on_press=lambda x, g=gname, r=req_user: self.accept_join(g, r))
                    row.add_widget(acc)
                    dec = Button(text="X", size_hint_x=0.25,
                                 background_color=(0.7, 0.2, 0.2, 1))
                    dec.bind(on_press=lambda x, g=gname, r=req_user: self.decline_join(g, r))
                    row.add_widget(dec)
                    self.list_container.add_widget(row)

            if not app.my_groups:
                self.list_container.add_widget(
                    Label(text="Нет групп. Введите имя + Добавить",
                          size_hint_y=None, height=40, color=(0.5, 0.5, 0.5, 1)))

            for g in app.my_groups:
                name = g["name"]
                is_admin = g.get("admin") == app.username
                badge = app.group_unread.get(name, 0)
                sub = f"{g.get('online', 0)}/{g.get('members', 0)}"
                text = f"{name}{' [А]' if is_admin else ''}  ({sub})"
                if badge > 0:
                    text += f"  ({badge})"
                row = Button(text=text, size_hint_y=None, height=50, halign="left")
                row.bind(on_press=lambda x, n=name: self.open_chat(n))
                self.list_container.add_widget(row)

        elif self.current_tab == "channels":
            if not app.my_channels:
                self.list_container.add_widget(
                    Label(text="Нет каналов. Введите имя + Добавить",
                          size_hint_y=None, height=40, color=(0.5, 0.5, 0.5, 1)))

            for c in app.my_channels:
                name = c["name"]
                is_admin = c.get("is_admin", False)
                sub = str(c.get("subscribers", 0))
                badge = app.channel_unread.get(name, 0)
                text = f"{name}{' [А]' if is_admin else ''}  ({sub})"
                if badge > 0:
                    text += f"  ({badge})"
                row = Button(text=text, size_hint_y=None, height=50, halign="left",
                             color=(0.9, 0.8, 0.3, 1))
                row.bind(on_press=lambda x, n=name: self.open_chat(n))
                self.list_container.add_widget(row)

    def do_add(self, *args):
        name = self.text_input.text.strip()
        if not name:
            self.show_status("Введите имя")
            return
        app = App.get_running_app()
        if self.current_tab == "contacts":
            if any(c["name"] == name for c in app.contacts):
                self.open_chat(name)
            elif name == app.username:
                self.show_status("Нельзя добавить себя")
            else:
                net.send({"action": "add_contact", "target": name})
                self.show_status(f"Заявка: {name}")
        elif self.current_tab == "groups":
            if any(g["name"] == name for g in app.my_groups):
                self.open_chat(name)
            else:
                # Отправляем заявку, а не вступаем сразу
                net.send({"action": "request_join_group", "name": name})
                self.show_status(f"Заявка отправлена. Ожидайте одобрения админом.")
        elif self.current_tab == "channels":
            if any(c["name"] == name for c in app.my_channels):
                self.open_chat(name)
            else:
                net.send({"action": "subscribe_channel", "name": name})
                self.show_status(f"Подписка: {name}")
        self.text_input.text = ""

    def do_create(self, *args):
        name = self.text_input.text.strip()
        if not name:
            self.show_status("Введите имя")
            return
        if self.current_tab == "groups":
            net.send({"action": "create_group", "name": name})
            self.show_status(f"Создание: {name}")
        elif self.current_tab == "channels":
            net.send({"action": "create_channel", "name": name})
            self.show_status(f"Создание: {name}")
        self.text_input.text = ""

    def accept_join(self, gname, username):
        net.send({"action": "accept_join", "name": gname, "target": username})
        self.show_status(f"Одобрен: {username} -> {gname}")

    def decline_join(self, gname, username):
        net.send({"action": "decline_join", "name": gname, "target": username})
        self.show_status(f"Отклонён: {username} <- {gname}")

    def open_chat(self, name):
        app = App.get_running_app()
        app.current_chat = name
        if self.current_tab == "contacts":
            if name in app.unread:
                del app.unread[name]
            net.send({"action": "open_chat", "target": name})
        elif self.current_tab == "groups":
            if name in app.group_unread:
                del app.group_unread[name]
            net.send({"action": "open_group", "name": name})
        elif self.current_tab == "channels":
            if name in app.channel_unread:
                del app.channel_unread[name]
            net.send({"action": "open_channel", "name": name})
        app.chat_tab = self.current_tab
        app.sm.current = "chat"

    def accept_contact(self, name):
        net.send({"action": "accept_contact", "target": name})
        self.show_status(f"Принят: {name}")

    def decline_contact(self, name):
        net.send({"action": "decline_contact", "target": name})
        self.show_status(f"Отклонён: {name}")

    def show_status(self, text):
        self.status_label.text = text
        Clock.schedule_once(lambda dt: setattr(self.status_label, "text", ""), 4)

# =========================================================
# ЭКРАН ЧАТА
# =========================================================
class ChatScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.build_ui()

    def build_ui(self):
        root = BoxLayout(orientation="vertical")

        header = BoxLayout(size_hint_y=0.1, spacing=5)
        back_btn = Button(text="< Назад", size_hint_x=0.25)
        back_btn.bind(on_press=lambda x: self.go_back())
        header.add_widget(back_btn)

        self.chat_title = Label(text="", size_hint_x=0.45, font_size=18)
        header.add_widget(self.chat_title)

        self.action_btn = Button(text="Удалить", size_hint_x=0.3,
                                   background_color=(0.7, 0.2, 0.2, 1))
        self.action_btn.bind(on_press=self.do_action)
        header.add_widget(self.action_btn)
        root.add_widget(header)

        # Панель админа — только для групп
        self.admin_box = BoxLayout(size_hint_y=0.08, spacing=5)
        self.add_member_btn = Button(text="+ Участник", size_hint_x=0.5,
                                       background_color=(0.2, 0.6, 0.2, 1))
        self.add_member_btn.bind(on_press=self.show_add_member)
        self.admin_box.add_widget(self.add_member_btn)

        self.kick_member_btn = Button(text="- Участник", size_hint_x=0.5,
                                        background_color=(0.6, 0.3, 0.2, 1))
        self.kick_member_btn.bind(on_press=self.show_kick_member)
        self.admin_box.add_widget(self.kick_member_btn)
        root.add_widget(self.admin_box)

        self.scroll = ScrollView(size_hint_y=0.72)
        self.msg_container = BoxLayout(orientation="vertical", size_hint_y=None, spacing=3)
        self.msg_container.bind(minimum_height=self.msg_container.setter("height"))
        self.scroll.add_widget(self.msg_container)
        root.add_widget(self.scroll)

        bottom = BoxLayout(size_hint_y=0.1, spacing=5, padding=5)
        self.msg_input = TextInput(hint_text="Сообщение", multiline=False, size_hint_x=0.7)
        bottom.add_widget(self.msg_input)
        self.send_btn = Button(text="Отправить", size_hint_x=0.3,
                                 background_color=(0.2, 0.6, 0.3, 1))
        self.send_btn.bind(on_press=self.send_msg)
        bottom.add_widget(self.send_btn)
        root.add_widget(bottom)

        self.add_widget(root)

    def on_enter(self):
        app = App.get_running_app()
        self.chat_title.text = app.current_chat
        tab = app.chat_tab

        self.admin_box.opacity = 0
        self.admin_box.height = 0
        self.admin_box.disabled = True

        if tab == "contacts":
            self.action_btn.text = "Удалить"
            self.action_btn.background_color = (0.7, 0.2, 0.2, 1)

        elif tab == "groups":
            g = next((g for g in app.my_groups if g["name"] == app.current_chat), None)
            if g and g.get("admin") == app.username:
                self.action_btn.text = "Удалить"
                self.action_btn.background_color = (0.7, 0.2, 0.2, 1)
                self.admin_box.opacity = 1
                self.admin_box.height = 50
                self.admin_box.disabled = False
            else:
                self.action_btn.text = "Покинуть"
                self.action_btn.background_color = (0.7, 0.5, 0.2, 1)

        elif tab == "channels":
            c = next((c for c in app.my_channels if c["name"] == app.current_chat), None)
            if c and c.get("is_admin"):
                self.action_btn.text = "Удалить"
                self.action_btn.background_color = (0.7, 0.2, 0.2, 1)
            else:
                self.action_btn.text = "Отписаться"
                self.action_btn.background_color = (0.7, 0.5, 0.2, 1)

        self.update_can_write()

    def update_can_write(self):
        app = App.get_running_app()
        tab = app.chat_tab
        can_write = True
        if tab == "channels":
            c = next((c for c in app.my_channels if c["name"] == app.current_chat), None)
            if c and not c.get("is_admin"):
                can_write = False
        self.msg_input.disabled = not can_write
        self.send_btn.disabled = not can_write
        self.msg_input.hint_text = "Сообщение" if can_write else "Только чтение"

    def refresh_messages(self):
        app = App.get_running_app()
        self.msg_container.clear_widgets()
        for msg in app.chat_messages[-50:]:
            sender = msg.get("from", "")
            text = msg.get("text", "")
            tm = msg.get("time", "")
            if sender == "СИСТЕМА":
                lbl = Label(text=f"  {text}", size_hint_y=None,
                            height=30, color=(0.8, 0.8, 0.3, 1), font_size=14, halign="left")
            else:
                is_me = sender == app.username
                color = (0.3, 0.9, 0.3, 1) if is_me else (0.4, 0.6, 0.9, 1)
                name = "Я" if is_me else sender
                lbl = Label(text=f"[{tm}] {name}: {text}", size_hint_y=None,
                            height=30, color=color, font_size=14, halign="left",
                            text_size=(Window.width - 40, None))
                lbl.bind(texture_size=lambda s, v: setattr(s, "height", max(30, v[1] + 5)))
            self.msg_container.add_widget(lbl)
        Clock.schedule_once(lambda dt: setattr(self.scroll, "scroll_y", 0))

    def send_msg(self, *args):
        app = App.get_running_app()
        text = self.msg_input.text.strip()
        if not text:
            return
        tab = app.chat_tab
        if tab == "contacts":
            net.send({"action": "msg", "target": app.current_chat, "text": text})
        elif tab == "groups":
            net.send({"action": "group_msg", "name": app.current_chat, "text": text})
        elif tab == "channels":
            net.send({"action": "channel_msg", "name": app.current_chat, "text": text})
        self.msg_input.text = ""

    def do_action(self, *args):
        app = App.get_running_app()
        tab = app.chat_tab
        if tab == "contacts":
            net.send({"action": "delete_chat", "target": app.current_chat})
        elif tab == "groups":
            g = next((g for g in app.my_groups if g["name"] == app.current_chat), None)
            if g and g.get("admin") == app.username:
                net.send({"action": "delete_group", "name": app.current_chat})
            else:
                net.send({"action": "leave_group", "name": app.current_chat})
                self.go_back()
        elif tab == "channels":
            c = next((c for c in app.my_channels if c["name"] == app.current_chat), None)
            if c and c.get("is_admin"):
                net.send({"action": "delete_channel", "name": app.current_chat})
            else:
                net.send({"action": "unsubscribe_channel", "name": app.current_chat})
                self.go_back()

    def show_add_member(self, *args):
        app = App.get_running_app()
        self.show_input_popup("Добавить участника", "Введите ник:", "Добавить",
                              lambda name: net.send({"action": "group_add_member",
                                                     "name": app.current_chat,
                                                     "target": name}))

    def show_kick_member(self, *args):
        app = App.get_running_app()
        self.show_input_popup("Удалить участника", "Введите ник:", "Удалить",
                              lambda name: net.send({"action": "group_kick",
                                                     "name": app.current_chat,
                                                     "target": name}))

    def show_input_popup(self, title, label, btn_text, callback):
        content = BoxLayout(orientation="vertical", spacing=5, padding=10)
        content.add_widget(Label(text=label, size_hint_y=0.3))
        inp = TextInput(multiline=False, size_hint_y=0.3)
        content.add_widget(inp)
        btns = BoxLayout(size_hint_y=0.3, spacing=5)
        ok = Button(text=btn_text)
        cancel = Button(text="Отмена")
        btns.add_widget(ok)
        btns.add_widget(cancel)
        content.add_widget(btns)
        popup = Popup(title=title, content=content, size_hint=(0.8, 0.4))
        ok.bind(on_press=lambda x: (callback(inp.text.strip()), popup.dismiss()))
        cancel.bind(on_press=popup.dismiss)
        popup.open()

    def go_back(self, *args):
        app = App.get_running_app()
        app.current_chat = ""
        app.chat_messages = []
        tab = app.chat_tab
        if tab == "contacts":
            net.send({"action": "request_contacts"})
        elif tab == "groups":
            net.send({"action": "request_groups"})
        elif tab == "channels":
            net.send({"action": "request_channels"})
        app.sm.current = "main"
        app.sm.get_screen("main").refresh_list()

# =========================================================
# ПРИЛОЖЕНИЕ
# =========================================================
class MessengerApp(App):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.username = ""
        self.contacts = []
        self.pending_in = []
        self.pending_out = []
        self.my_groups = []
        self.my_channels = []
        self.unread = {}
        self.group_unread = {}
        self.channel_unread = {}
        self.current_chat = ""
        self.chat_messages = []
        self.chat_tab = "contacts"
        # Заявки на вступление в группы (для админа)
        self.group_join_requests = {}

    def build(self):
        self.sm = ScreenManager()
        self.sm.add_widget(AuthScreen(name="auth"))
        self.sm.add_widget(MainScreen(name="main"))
        self.sm.add_widget(ChatScreen(name="chat"))

        try:
            net.connect()
        except Exception as e:
            print(f"Не удалось подключиться: {e}")

        Clock.schedule_interval(self.poll_packets, 0.05)
        return self.sm

    def poll_packets(self, dt):
        while True:
            pkt = net.get_packet()
            if pkt == "EMPTY":
                return True
            if pkt is None:
                print("Сервер отключился")
                return True

            t = pkt.get("type")

            if t == "auth_ok":
                auth_screen = self.sm.get_screen("auth")
                auth_screen.on_auth_ok(pkt.get("username", ""))
            elif t == "auth_error":
                auth_screen = self.sm.get_screen("auth")
                auth_screen.on_auth_error(pkt.get("text", "Ошибка"))
            elif t == "banned":
                auth_screen = self.sm.get_screen("auth")
                auth_screen.on_banned(pkt.get("text", "Заблокирован"))

            elif t == "contacts_data":
                self.contacts = pkt.get("contacts", [])
                self.pending_in = pkt.get("pending_in", [])
                self.pending_out = pkt.get("pending_out", [])
                if self.sm.current == "main":
                    self.sm.get_screen("main").refresh_list()

            elif t == "groups_data":
                self.my_groups = pkt.get("groups", [])
                if self.sm.current == "main":
                    self.sm.get_screen("main").refresh_list()

            elif t == "group_join_requests":
                gname = pkt.get("group", "")
                reqs = pkt.get("requests", [])
                if reqs:
                    self.group_join_requests[gname] = reqs
                elif gname in self.group_join_requests:
                    del self.group_join_requests[gname]
                if self.sm.current == "main":
                    self.sm.get_screen("main").refresh_list()

            elif t == "channels_data":
                self.my_channels = pkt.get("channels", [])
                if self.sm.current == "main":
                    self.sm.get_screen("main").refresh_list()

            elif t == "history":
                if self.sm.current == "chat" and self.chat_tab == "contacts" and pkt.get("target") == self.current_chat:
                    self.chat_messages = pkt.get("data", [])
                    self.sm.get_screen("chat").refresh_messages()

            elif t == "group_history":
                if self.sm.current == "chat" and self.chat_tab == "groups" and pkt.get("group") == self.current_chat:
                    self.chat_messages = pkt.get("data", [])
                    self.sm.get_screen("chat").refresh_messages()

            elif t == "channel_history":
                if self.sm.current == "chat" and self.chat_tab == "channels" and pkt.get("channel") == self.current_chat:
                    self.chat_messages = pkt.get("data", [])
                    self.sm.get_screen("chat").refresh_messages()

            elif t == "msg":
                sender = pkt.get("from", "")
                text = pkt.get("text", "")
                tm = pkt.get("time", "")
                if self.sm.current == "chat" and self.chat_tab == "contacts" and sender == self.current_chat:
                    self.chat_messages.append({"from": sender, "text": text, "time": tm})
                    self.sm.get_screen("chat").refresh_messages()
                else:
                    self.unread[sender] = self.unread.get(sender, 0) + 1

            elif t == "msg_sent":
                if self.sm.current == "chat" and self.chat_tab == "contacts" and pkt.get("to") == self.current_chat:
                    self.chat_messages.append({"from": self.username, "text": pkt.get("text", ""), "time": pkt.get("time", "")})
                    self.sm.get_screen("chat").refresh_messages()

            elif t == "group_msg":
                gname = pkt.get("group", "")
                sender = pkt.get("from", "")
                text = pkt.get("text", "")
                tm = pkt.get("time", "")
                if self.sm.current == "chat" and self.chat_tab == "groups" and gname == self.current_chat:
                    self.chat_messages.append({"from": sender, "text": text, "time": tm})
                    self.sm.get_screen("chat").refresh_messages()
                else:
                    self.group_unread[gname] = self.group_unread.get(gname, 0) + 1

            elif t == "channel_msg":
                cname = pkt.get("channel", "")
                sender = pkt.get("from", "")
                text = pkt.get("text", "")
                tm = pkt.get("time", "")
                if self.sm.current == "chat" and self.chat_tab == "channels" and cname == self.current_chat:
                    self.chat_messages.append({"from": sender, "text": text, "time": tm})
                    self.sm.get_screen("chat").refresh_messages()
                else:
                    self.channel_unread[cname] = self.channel_unread.get(cname, 0) + 1

            elif t == "group_system":
                gname = pkt.get("group", "")
                text = pkt.get("text", "")
                if self.sm.current == "chat" and self.chat_tab == "groups" and gname == self.current_chat:
                    self.chat_messages.append({"from": "СИСТЕМА", "text": text, "time": time.strftime("%H:%M:%S")})
                    self.sm.get_screen("chat").refresh_messages()

            elif t == "join_accepted":
                gname = pkt.get("group", "")
                if self.sm.current == "main":
                    self.sm.get_screen("main").show_status(f"Вас приняли в группу: {gname}")
                else:
                    print(f"Принят в группу: {gname}")

            elif t == "join_declined":
                gname = pkt.get("group", "")
                if self.sm.current == "main":
                    self.sm.get_screen("main").show_status(f"Заявка отклонена: {gname}")
                else:
                    print(f"Заявка отклонена: {gname}")

            elif t == "info":
                if self.sm.current == "main":
                    self.sm.get_screen("main").show_status(pkt.get("text", ""))

            elif t == "chat_deleted":
                if self.sm.current == "chat" and pkt.get("target") == self.current_chat:
                    self.current_chat = ""
                    self.chat_messages = []
                    net.send({"action": "request_contacts"})
                    self.sm.current = "main"
                    self.sm.get_screen("main").refresh_list()

            elif t == "group_deleted":
                gname = pkt.get("group", "")
                if self.sm.current == "chat" and gname == self.current_chat:
                    self.current_chat = ""
                    self.chat_messages = []
                    self.sm.current = "main"
                self.my_groups = [g for g in self.my_groups if g["name"] != gname]
                if gname in self.group_join_requests:
                    del self.group_join_requests[gname]
                if self.sm.current == "main":
                    self.sm.get_screen("main").refresh_list()

            elif t == "channel_deleted":
                cname = pkt.get("channel", "")
                if self.sm.current == "chat" and cname == self.current_chat:
                    self.current_chat = ""
                    self.chat_messages = []
                    self.sm.current = "main"
                self.my_channels = [c for c in self.my_channels if c["name"] != cname]
                if self.sm.current == "main":
                    self.sm.get_screen("main").refresh_list()

            elif t == "group_created":
                if self.sm.current == "main":
                    self.sm.get_screen("main").show_status(f"Группа: {pkt.get('name')}")

            elif t == "channel_created":
                if self.sm.current == "main":
                    self.sm.get_screen("main").show_status(f"Канал: {pkt.get('name')}")

            elif t == "group_joined":
                if self.sm.current == "main":
                    self.sm.get_screen("main").show_status(f"В группе: {pkt.get('name')}")

            elif t == "channel_subscribed":
                if self.sm.current == "main":
                    self.sm.get_screen("main").show_status(f"Подписка: {pkt.get('name')}")

            elif t == "error":
                if self.sm.current == "main":
                    self.sm.get_screen("main").show_status(pkt.get("text", "Ошибка"))

if __name__ == "__main__":
    MessengerApp().run()
