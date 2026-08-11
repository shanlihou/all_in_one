import sys
import json
import os
import time
from datetime import datetime
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLineEdit, QPushButton, QTableWidget, QTableWidgetItem,
    QComboBox, QLabel, QHeaderView, QPlainTextEdit, QSplitter,
    QAbstractItemView, QMessageBox
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from aliyun.log import LogClient, GetLogsRequest


TIME_PRESETS = [
    ("最近 5 分钟", 5),
    ("最近 15 分钟", 15),
    ("最近 1 小时", 60),
    ("最近 6 小时", 360),
    ("最近 24 小时", 1440),
]


class QueryWorker(QThread):
    finished = pyqtSignal(list, int)
    error = pyqtSignal(str)

    def __init__(self, client, project, logstore, query,
                 from_time, to_time, offset, line):
        super().__init__()
        self.client = client
        self.project = project
        self.logstore = logstore
        self.query = query
        self.from_time = from_time
        self.to_time = to_time
        self.offset = offset
        self.line = line

    def run(self):
        try:
            request = GetLogsRequest(
                self.project,
                self.logstore,
                self.from_time,
                self.to_time,
                '',
                self.query,
                self.line,
                self.offset,
                False,
            )
            response = self.client.get_logs(request)
            logs = response.get_logs()
            total = response.get_count()
            self.finished.emit(logs, total)
        except Exception as e:
            self.error.emit(str(e))


class MainWindow(QMainWindow):
    def __init__(self, config):
        super().__init__()
        self.config = config
        self.client = LogClient(
            config['endpoint'],
            config['access_key_id'],
            config['access_key'],
        )
        self.worker = None
        self.total_count = 0
        self.current_page = 0
        self.page_size = 50

        self.setWindowTitle('SLS 日志查看器  -  {}/{}'.format(
            config.get('project', ''), config.get('logstore', '')
        ))
        self.resize(1200, 720)
        self._build_ui()
        self._update_pagination_labels()

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        bar = QHBoxLayout()
        bar.setSpacing(6)

        bar.addWidget(QLabel('时间:'))
        self.time_combo = QComboBox()
        for label, _ in TIME_PRESETS:
            self.time_combo.addItem(label)
        self.time_combo.setCurrentIndex(1)
        bar.addWidget(self.time_combo)

        bar.addSpacing(8)
        bar.addWidget(QLabel('查询:'))
        self.query_edit = QLineEdit()
        self.query_edit.setPlaceholderText(
            '输入 SLS 查询语句，例如 _doRandomTeleporter 或 level:ERROR；回车搜索'
        )
        self.query_edit.returnPressed.connect(self.on_search)
        bar.addWidget(self.query_edit, 1)

        self.search_btn = QPushButton('搜索')
        self.search_btn.clicked.connect(self.on_search)
        bar.addWidget(self.search_btn)

        layout.addLayout(bar)

        splitter = QSplitter(Qt.Vertical)

        self.table = QTableWidget()
        self.table.setColumnCount(2)
        self.table.setHorizontalHeaderLabels(['时间', '内容'])
        self.table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeToContents
        )
        self.table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.Stretch
        )
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.itemSelectionChanged.connect(self.on_row_selected)
        splitter.addWidget(self.table)

        self.detail = QPlainTextEdit()
        self.detail.setReadOnly(True)
        self.detail.setPlaceholderText('选中上面表格中的一行以查看完整内容')
        splitter.addWidget(self.detail)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)

        layout.addWidget(splitter, 1)

        pager = QHBoxLayout()
        self.prev_btn = QPushButton('< 上一页')
        self.prev_btn.clicked.connect(self.on_prev)
        pager.addWidget(self.prev_btn)

        self.page_label = QLabel('')
        self.page_label.setMinimumWidth(120)
        self.page_label.setAlignment(Qt.AlignCenter)
        pager.addWidget(self.page_label)

        self.next_btn = QPushButton('下一页 >')
        self.next_btn.clicked.connect(self.on_next)
        pager.addWidget(self.next_btn)

        pager.addStretch()

        pager.addWidget(QLabel('每页:'))
        self.page_size_combo = QComboBox()
        self.page_size_combo.addItems(['20', '50', '100', '200'])
        self.page_size_combo.setCurrentIndex(1)
        self.page_size_combo.currentIndexChanged.connect(self.on_page_size_change)
        pager.addWidget(self.page_size_combo)

        self.total_label = QLabel('共 0 条')
        self.total_label.setMinimumWidth(120)
        self.total_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        pager.addWidget(self.total_label)

        layout.addLayout(pager)

        self.statusBar().showMessage('就绪，请在搜索框输入查询条件后按回车或点击「搜索」')

    def get_time_range(self):
        idx = self.time_combo.currentIndex()
        minutes = TIME_PRESETS[idx][1]
        to_time = int(time.time())
        from_time = to_time - minutes * 60
        return from_time, to_time

    def on_search(self):
        if self.worker and self.worker.isRunning():
            return
        self.current_page = 0
        self._run_query()

    def on_prev(self):
        if self.current_page > 0:
            self.current_page -= 1
            self._run_query()

    def on_next(self):
        if (self.current_page + 1) * self.page_size < self.total_count:
            self.current_page += 1
            self._run_query()

    def on_page_size_change(self):
        self.page_size = int(self.page_size_combo.currentText())
        self.current_page = 0
        if self.worker and self.worker.isRunning():
            return
        self._run_query()

    def on_row_selected(self):
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return
        row = rows[0].row()
        item = self.table.item(row, 1)
        if item:
            self.detail.setPlainText(item.text())

    def _run_query(self):
        query = self.query_edit.text().strip()
        from_time, to_time = self.get_time_range()
        offset = self.current_page * self.page_size

        self.statusBar().showMessage('查询中...')
        self.search_btn.setEnabled(False)
        self.prev_btn.setEnabled(False)
        self.next_btn.setEnabled(False)
        self.table.setRowCount(0)
        self.detail.clear()

        self.worker = QueryWorker(
            self.client,
            self.config['project'],
            self.config['logstore'],
            query,
            from_time,
            to_time,
            offset,
            self.page_size,
        )
        self.worker.finished.connect(self.on_query_done)
        self.worker.error.connect(self.on_query_error)
        self.worker.start()

    def on_query_done(self, logs, total):
        self.total_count = total
        self.table.setRowCount(len(logs))
        for i, log in enumerate(logs):
            contents = dict(log.contents)
            content_str = (
                contents.get('content', '')
                or contents.get('message', '')
                or contents.get('__raw__', '')
            )
            ts_ms = contents.get('__time__', '')
            ts_text = ''
            if ts_ms:
                try:
                    ts_text = datetime.fromtimestamp(
                        int(ts_ms) / 1000
                    ).strftime('%Y-%m-%d %H:%M:%S')
                except Exception:
                    ts_text = str(ts_ms)

            self.table.setItem(i, 0, QTableWidgetItem(ts_text))
            self.table.setItem(i, 1, QTableWidgetItem(content_str))

        self._update_pagination_labels()

        self.search_btn.setEnabled(True)
        self.statusBar().showMessage(
            '查询完成: 当前页 {} 条，总计 {} 条'.format(len(logs), total)
        )

    def on_query_error(self, msg):
        self.search_btn.setEnabled(True)
        self.total_count = 0
        self._update_pagination_labels()
        self.statusBar().showMessage('查询失败: {}'.format(msg))
        QMessageBox.critical(self, '查询失败', msg)

    def _update_pagination_labels(self):
        total_pages = max(1, (self.total_count + self.page_size - 1) // self.page_size)
        if self.total_count == 0:
            total_pages = 1
        self.page_label.setText(
            '第 {} / {} 页'.format(self.current_page + 1, total_pages)
        )
        self.total_label.setText('共 {} 条'.format(self.total_count))
        self.prev_btn.setEnabled(self.current_page > 0)
        self.next_btn.setEnabled(
            (self.current_page + 1) * self.page_size < self.total_count
        )


def load_config():
    candidates = ['.config.json', '.config.example.json']
    here = os.path.dirname(os.path.abspath(__file__))
    for name in candidates:
        path = os.path.join(here, name)
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
    raise FileNotFoundError(
        '未找到配置文件，请在 {} 下创建 .config.json'.format(here)
    )


def main():
    config = load_config()
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    win = MainWindow(config)
    win.show()
    sys.exit(app.exec_())


if __name__ == '__main__':
    main()