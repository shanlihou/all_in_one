import sys
import json
import os
import time
from datetime import datetime
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QTableWidget, QTableWidgetItem,
    QComboBox, QLabel, QHeaderView, QPlainTextEdit, QSplitter,
    QAbstractItemView, QMessageBox, QMenu, QAction,
    QDateTimeEdit
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QDateTime
from PyQt5.QtGui import QKeySequence
from aliyun.log import LogClient, GetLogsRequest


HERE = os.path.dirname(os.path.abspath(__file__))
HISTORY_PATH = os.path.join(HERE, '.search_history.json')
HISTORY_MAX = 50

TIME_PRESETS = [
    ("最近 5 分钟", 5),
    ("最近 15 分钟", 15),
    ("最近 1 小时", 60),
    ("最近 6 小时", 360),
    ("最近 24 小时", 1440),
]
CUSTOM_RANGE_INDEX = len(TIME_PRESETS)

DEFAULT_EVENTS = [
    ("传送", "_doRandomTeleporter"),
    ("玩家死亡", "onCellAppDeath"),
    ("矿战", "mine_war"),
    ("怪物", "monster"),
    ("错误", "level:ERROR"),
]


def load_history():
    if not os.path.exists(HISTORY_PATH):
        return []
    try:
        with open(HISTORY_PATH, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return [str(x) for x in data] if isinstance(data, list) else []
    except Exception:
        return []


def save_history(history):
    try:
        with open(HISTORY_PATH, 'w', encoding='utf-8') as f:
            json.dump(history[:HISTORY_MAX], f, ensure_ascii=False, indent=2)
    except Exception as e:
        print('保存搜索历史失败: {}'.format(e))


def push_history(history, query):
    query = query.strip()
    if not query:
        return history
    history = [q for q in history if q != query]
    history.insert(0, query)
    return history[:HISTORY_MAX]


def parse_events(raw):
    if not isinstance(raw, list):
        return []
    parsed = []
    for item in raw:
        if isinstance(item, (list, tuple)) and len(item) >= 2:
            label, query = item[0], item[1]
            if query:
                parsed.append((str(label), str(query)))
        elif isinstance(item, dict):
            query = item.get('query') or item.get('value') or ''
            if not query:
                continue
            label = (item.get('label') or item.get('name')
                     or item.get('title') or str(query))
            parsed.append((str(label), str(query)))
    return parsed


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
        self.history = load_history()
        self.events = parse_events(config.get('events')) or DEFAULT_EVENTS

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
        self.time_combo.addItem('自定义...')
        self.time_combo.setCurrentIndex(1)
        self.time_combo.currentIndexChanged.connect(self.on_time_mode_change)
        bar.addWidget(self.time_combo)

        bar.addSpacing(8)
        bar.addWidget(QLabel('查询:'))
        self.query_combo = QComboBox()
        self.query_combo.setEditable(True)
        self.query_combo.setInsertPolicy(QComboBox.NoInsert)
        self.query_combo.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        if self.history:
            self.query_combo.addItems(self.history)
        line_edit = self.query_combo.lineEdit()
        line_edit.setPlaceholderText(
            '输入 SLS 查询语句（例: _doRandomTeleporter 或 level:ERROR），回车搜索；'
            '下拉框显示历史搜索'
        )
        line_edit.returnPressed.connect(self.on_search)
        bar.addWidget(self.query_combo, 1)

        self.search_btn = QPushButton('搜索')
        self.search_btn.clicked.connect(self.on_search)
        bar.addWidget(self.search_btn)

        layout.addLayout(bar)

        self.custom_range_row = QWidget()
        custom_layout = QHBoxLayout(self.custom_range_row)
        custom_layout.setContentsMargins(0, 0, 0, 0)
        custom_layout.setSpacing(6)

        custom_layout.addWidget(QLabel('从:'))
        self.from_dt = QDateTimeEdit(QDateTime.currentDateTime().addSecs(-3600))
        self.from_dt.setCalendarPopup(True)
        self.from_dt.setDisplayFormat('yyyy-MM-dd HH:mm:ss')
        self.from_dt.setMinimumDateTime(QDateTime.fromSecsSinceEpoch(0))
        custom_layout.addWidget(self.from_dt)

        custom_layout.addWidget(QLabel('至:'))
        self.to_dt = QDateTimeEdit(QDateTime.currentDateTime())
        self.to_dt.setCalendarPopup(True)
        self.to_dt.setDisplayFormat('yyyy-MM-dd HH:mm:ss')
        self.to_dt.setMinimumDateTime(QDateTime.fromSecsSinceEpoch(0))
        custom_layout.addWidget(self.to_dt)

        custom_layout.addSpacing(12)
        custom_layout.addWidget(QLabel('快速:'))
        for label, kind in [('近 1 小时', '1h'),
                            ('今天', 'today'),
                            ('昨天', 'yesterday')]:
            btn = QPushButton(label)
            btn.clicked.connect(lambda checked=False, k=kind: self.on_quick_range(k))
            custom_layout.addWidget(btn)

        custom_layout.addStretch()
        self.apply_range_btn = QPushButton('应用时间范围')
        self.apply_range_btn.clicked.connect(self.on_apply_range)
        custom_layout.addWidget(self.apply_range_btn)

        self.custom_range_row.setVisible(False)
        layout.addWidget(self.custom_range_row)

        events_row = QHBoxLayout()
        events_row.setSpacing(6)
        events_row.addWidget(QLabel('快捷事件:'))
        for label, query in self.events:
            btn = QPushButton(label)
            btn.setToolTip(query)
            btn.clicked.connect(lambda checked=False, q=query: self.on_event_click(q))
            events_row.addWidget(btn)
        events_row.addStretch()
        self.clear_history_btn = QPushButton('清空历史')
        self.clear_history_btn.clicked.connect(self.on_clear_history)
        events_row.addWidget(self.clear_history_btn)
        layout.addLayout(events_row)

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
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self.on_table_context_menu)

        self._copy_action = QAction('复制选中行', self.table)
        self._copy_action.setShortcut(QKeySequence.Copy)
        self._copy_action.setShortcutContext(Qt.WidgetShortcut)
        self._copy_action.triggered.connect(self.copy_selected_rows)
        self.table.addAction(self._copy_action)

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
        if idx == CUSTOM_RANGE_INDEX:
            from_ts = int(self.from_dt.dateTime().toSecsSinceEpoch())
            to_ts = int(self.to_dt.dateTime().toSecsSinceEpoch())
            return from_ts, to_ts
        minutes = TIME_PRESETS[idx][1]
        to_time = int(time.time())
        from_time = to_time - minutes * 60
        return from_time, to_time

    def format_range_label(self):
        idx = self.time_combo.currentIndex()
        if idx == CUSTOM_RANGE_INDEX:
            from_str = self.from_dt.dateTime().toString('yyyy-MM-dd HH:mm:ss')
            to_str = self.to_dt.dateTime().toString('yyyy-MM-dd HH:mm:ss')
            return '{} ~ {}'.format(from_str, to_str)
        return TIME_PRESETS[idx][0]

    def on_time_mode_change(self, idx):
        self.custom_range_row.setVisible(idx == CUSTOM_RANGE_INDEX)
        if idx == CUSTOM_RANGE_INDEX:
            now = QDateTime.currentDateTime()
            if self.from_dt.dateTime().secsTo(now) < 0:
                self.from_dt.setDateTime(now.addSecs(-3600))
            if self.to_dt.dateTime().secsTo(now) < -10:
                self.to_dt.setDateTime(now)

    def on_quick_range(self, kind):
        now = QDateTime.currentDateTime()
        if kind == '1h':
            self.from_dt.setDateTime(now.addSecs(-3600))
            self.to_dt.setDateTime(now)
        elif kind == 'today':
            from PyQt5.QtCore import QTime
            today = now.date()
            self.from_dt.setDateTime(QDateTime(today, QTime(0, 0, 0)))
            self.to_dt.setDateTime(now)
        elif kind == 'yesterday':
            from PyQt5.QtCore import QTime
            yesterday = now.date().addDays(-1)
            self.from_dt.setDateTime(QDateTime(yesterday, QTime(0, 0, 0)))
            self.to_dt.setDateTime(QDateTime(yesterday, QTime(23, 59, 59)))

    def on_apply_range(self):
        if self.from_dt.dateTime() >= self.to_dt.dateTime():
            QMessageBox.warning(
                self, '时间范围无效', '起始时间必须早于结束时间'
            )
            return
        if self.worker and self.worker.isRunning():
            return
        self.current_page = 0
        self._run_query()

    def on_search(self):
        if self.worker and self.worker.isRunning():
            return
        query = self.query_combo.currentText().strip()
        self._record_history(query)
        self.current_page = 0
        self._run_query()

    def _record_history(self, query):
        if not query:
            return
        if query in self.history:
            return
        self.history = push_history(self.history, query)
        self.query_combo.insertItem(0, query)
        self.query_combo.setCurrentIndex(0)
        save_history(self.history)

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

    def on_event_click(self, query):
        self.query_combo.setCurrentText(query)
        self.on_search()

    def on_clear_history(self):
        if not self.history:
            self.statusBar().showMessage('历史已为空', 3000)
            return
        reply = QMessageBox.question(
            self, '清空历史', '确定要清空所有搜索历史吗？',
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return
        self.history = []
        save_history(self.history)
        self.query_combo.clear()
        self.query_combo.lineEdit().setPlaceholderText(
            '输入 SLS 查询语句（例: _doRandomTeleporter 或 level:ERROR），回车搜索；'
            '下拉框显示历史搜索'
        )
        self.statusBar().showMessage('搜索历史已清空', 3000)

    def on_table_context_menu(self, pos):
        if not self.table.selectionModel().selectedRows():
            return
        menu = QMenu(self.table)
        menu.addAction(self._copy_action)
        copy_all = menu.addAction('复制全部行')
        chosen = menu.exec_(self.table.viewport().mapToGlobal(pos))
        if chosen == copy_all:
            self.copy_all_rows()

    def copy_selected_rows(self):
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            self.statusBar().showMessage('未选中任何行', 3000)
            return
        lines = []
        for idx in sorted(r.row() for r in rows):
            ts_item = self.table.item(idx, 0)
            content_item = self.table.item(idx, 1)
            ts = ts_item.text() if ts_item else ''
            content = content_item.text() if content_item else ''
            lines.append('{}\t{}'.format(ts, content) if ts else content)
        QApplication.clipboard().setText('\n'.join(lines))
        self.statusBar().showMessage(
            '已复制 {} 行到剪贴板'.format(len(rows)), 3000
        )

    def copy_all_rows(self):
        if self.table.rowCount() == 0:
            self.statusBar().showMessage('当前页无内容可复制', 3000)
            return
        lines = []
        for i in range(self.table.rowCount()):
            ts_item = self.table.item(i, 0)
            content_item = self.table.item(i, 1)
            ts = ts_item.text() if ts_item else ''
            content = content_item.text() if content_item else ''
            lines.append('{}\t{}'.format(ts, content) if ts else content)
        QApplication.clipboard().setText('\n'.join(lines))
        self.statusBar().showMessage(
            '已复制当前页 {} 行到剪贴板'.format(self.table.rowCount()), 3000
        )

    def _run_query(self):
        query = self.query_combo.currentText().strip()
        from_time, to_time = self.get_time_range()
        offset = self.current_page * self.page_size

        self.statusBar().showMessage('查询中... [{}]'.format(self.format_range_label()))
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