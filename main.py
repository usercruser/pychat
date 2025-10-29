import os
import sys
import time
import uuid

import firebase_admin
from firebase_admin import credentials
from firebase_admin import db

from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QLineEdit, 
    QPushButton, QTextEdit, QInputDialog, QMessageBox,
    QDialog, QLabel, QGridLayout
)
from PyQt5.QtCore import QThread, pyqtSignal, Qt, QObject

os.getcwd()

SERVICE_ACCOUNT_KEY_PATH = "pychatgui-1e64d-firebase-adminsdk-fbsvc-447b534fba.json" 
DATABASE_URL = 'https://pychatgui-1e64d-default-rtdb.asia-southeast1.firebasedatabase.app/'

try:
    cred = credentials.Certificate(SERVICE_ACCOUNT_KEY_PATH)
    firebase_admin.initialize_app(cred, {'databaseURL': DATABASE_URL})
    ROOMS_DB_REF = db.reference('rooms')
    
except Exception as e:
    print(f"치명적 오류! - firebase 연결 초기화 실패: {e}")
    sys.exit(1)
pass

class FirebaseListenerThread(QThread):
    messageReceived = pyqtSignal(str) 

    def __init__(self, ref: db.Reference, parent=None):
        super().__init__(parent)
        self.ref = ref
        self._is_running = True
        self.listener_stream = None

    def handleMessage(self, event):
        if event.event_type == 'put':
            messagesData = self.ref.get()
            
            if messagesData:
                sortedMessages = sorted(messagesData.items(), key=lambda item: item[1].get('timestamp', 0))
                fullChatHis = ""
                for _, msg in sortedMessages:
                    sender = msg.get('sender', 'Unknown')
                    content = msg.get('message', 'No Content')
                    fullChatHis += f"[{sender}]: {content}\n"
                self.messageReceived.emit(fullChatHis.strip())

    def run(self):
        print(f"정보: firebase listner 스레드 시작됨 - 채팅 db 경로 : {self.ref.path}")
        try:
            self.listener_stream = self.ref.listen(self.handleMessage)
        except Exception as e:
            print(f"오류: firebase listner 시작 실패: {e}")
            return
            
        self.exec()

    def stop(self):
        if self.listener_stream:
            self.listener_stream.close()
            print("정보: firebase listner 스트림 종료됨")
        self._is_running = False
        self.quit()
        self.wait()
        
class ChatStartupDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('PyChat GUI BETA')
        self.setGeometry(200, 200, 350, 250)
        
        self.roomid = None
        self.roomname = None
        self.username = None

        self.initUI()
        
    def initUI(self):
        layout = QGridLayout()
        self.setGeometry(100, 100, 500, 700)
        self.setStyleSheet("""
            QWidget { background-color: #1a1b26; }
            QTextEdit { 
                border: 1px solid #ccc; 
                padding: 10px; 
                font-size: 14px;
                background-color: #16161e;
            }
            QLineEdit { 
                padding: 8px; 
                border: 1px solid #ddd;
                font-size: 14px;
                background-color: #16161e;
            }
            QPushButton {
                background-color: #978ff9;
                color: white;
                padding: 10px;
                border: none;
                border-radius: 5px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #614c8f; }
        """)

        self.settingButton = QPushButton

        layout.addWidget(QLabel('닉네임 : '), 0, 0)
        self.nicknameInput = QLineEdit()
        self.nicknameInput.setPlaceholderText('닉네임 입력...')
        layout.addWidget(self.nicknameInput, 0, 1)

        layout.addWidget(QLabel('채팅방 이름 : '), 1, 0)
        self.roomNameInput = QLineEdit()
        self.roomNameInput.setPlaceholderText('방 이름 입력... (또는 생성)')
        layout.addWidget(self.roomNameInput, 1, 1)

        layout.addWidget(QLabel('방 비밀번호 : '), 2, 0)
        self.passwordInput = QLineEdit()
        self.passwordInput.setEchoMode(QLineEdit.Password)
        self.passwordInput.setPlaceholderText('비밀번호 입력...')
        layout.addWidget(self.passwordInput, 2, 1)

        self.enterButton = QPushButton('입장')
        self.enterButton.clicked.connect(self.attemptConnection)
        layout.addWidget(self.enterButton, 3, 0, 1, 2)

        self.setLayout(layout)
        
    def attemptConnection(self):
        roomname = self.roomNameInput.text().strip()
        password = self.passwordInput.text().strip()
        username = self.nicknameInput.text().strip()

        if not roomname or not password or not username:
            QMessageBox.warning(self, "오류", "모든 입력란을 체워주세요")
            return

        roomid = roomname.replace('.', '_').replace('#', '_').replace('$', '_').replace('[', '_').replace(']', '_')

        roomref = ROOMS_DB_REF.child(roomid)
        roominfo = roomref.get()

        if roominfo is None:
            QMessageBox.information(self, "안내", f"'{roomname}' 방이 존재하지 않아 새로 생성할게요")
            try:
                roomref.set({
                    'name': roomname,
                    'password': password,
                    'creator': username,
                    'createdAt': int(time.time() * 1000)
                })
                self.finalizeConnection(roomid, roomname, username)
            except Exception as e:
                QMessageBox.critical(self, "오류", f"방 생성에 실패했어요: {e}")
        else:
            if roominfo.get('password') == password:
                self.finalizeConnection(roomid, roomname, username)
            else:
                QMessageBox.critical(self, "오류", "인증에 실패했어요: 비밀번호가 일치하지 않아요")

    def finalizeConnection(self, roomid, roomname, username):
        self.roomid = roomid
        self.roomname = roomname
        self.username = username
        self.accept()

class ChatWindow(QWidget):
    def __init__(self, roomid: str, roomname: str, username: str):
        super().__init__()
        
        self.roomref = db.reference(f'chats/{roomid}/messages')
        self.roomname = roomname
        self.username = username
        self.listener_thread = None
        
        self.initUI()
        self.start_listener()

    def initUI(self):
        self.setWindowTitle(f'PyChat GUI BETA - 실시간 채팅 [{self.roomname}] (닉네임 : {self.username})')
        self.setGeometry(100, 100, 500, 700)
        self.setStyleSheet("""
            QWidget { background-color: #1a1b26; }
            QTextEdit { 
                border: 1px solid #ccc; 
                font-size: 14px;
                padding: 10px;
                background-color: #16161e;
            }
            QLineEdit { 
                padding: 8px; 
                border: 1px solid #ddd;
                font-size: 14px;
                background-color: #16161e;
            }
            QPushButton {
                background-color: #978ff9;
                color: white;
                padding: 10px;
                border: none;
                border-radius: 5px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #614c8f; }
        """)

        vbox = QVBoxLayout()
        
        self.chatDisplay = QTextEdit()
        self.chatDisplay.setReadOnly(True)
        vbox.addWidget(self.chatDisplay)

        self.messageInput = QLineEdit()
        self.messageInput.setPlaceholderText("메시지를 입력하세요...")
        vbox.addWidget(self.messageInput)
        
        self.sendButton = QPushButton('메시지 전송')
        vbox.addWidget(self.sendButton)
        
        self.setLayout(vbox)

        self.sendButton.clicked.connect(self.sendMessage)
        self.messageInput.returnPressed.connect(self.sendMessage) 

    def sendMessage(self):
        text = self.messageInput.text().strip()
        
        if not text:
            QMessageBox.warning(self, "경고", "공백은 전송할 수 없어요")
            return

        messageData = {
            'sender': self.username,
            'message': text,
        }

        try:
            self.roomref.push(messageData)
            self.messageInput.clear()
        except Exception as e:
            QMessageBox.critical(self, "전송 오류", f"메시지 전송 실패: {e}")
            print(f"ERROR: Error sending message: {e}")
            
    def start_listener(self):
        if self.listener_thread:
            self.listener_thread.stop()
        
        self.listener_thread = FirebaseListenerThread(self.roomref)
        self.listener_thread.messageReceived.connect(self.add_message_to_gui)
        self.listener_thread.start()

    def add_message_to_gui(self, full_history: str):
        self.chatDisplay.setText(full_history)
        scrollbar = self.chatDisplay.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def closeEvent(self, event):
        if self.listener_thread:
            self.listener_thread.stop()
        event.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    
    startupDialog = ChatStartupDialog()
    
    if startupDialog.exec_() == QDialog.Accepted:
        roomid = startupDialog.roomid
        roomname = startupDialog.roomname
        username = startupDialog.username

        window = ChatWindow(roomid, roomname, username)
        window.show()
        
        sys.exit(app.exec_())
    else:
        sys.exit(0)
