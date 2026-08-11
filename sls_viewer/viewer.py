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
    QDateTimeEdit, QSpinBox
)
from PyQt5.QtGui import QFont
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QDateTime
from PyQt5.QtGui import QKeySequence
from aliyun.log import LogClient, GetLogsRequest


HERE = os.path.dirname(os.path.abspath(__file__))
HISTORY_PATH = os.path.join(HERE, '.search_history.json')
HISTORY_MAX = 50
RANGE_HISTORY_PATH = os.path.join(HERE, '.range_history.json')
RANGE_HISTORY_MAX = 20
LOG_PATH = os.path.join(HERE, 'sls_viewer.log')
LOG_MAX_BYTES = 10 * 1024 * 1024

TIME_PRESETS = [
    ("最近 5 分钟", 5),
    ("最近 15 分钟", 15),
    ("最近 1 小时", 60),
    ("最近 6 小时", 360),
    ("最近 24 小时", 1440),
]
CUSTOM_RANGE_INDEX = len(TIME_PRESETS)


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


def load_range_history():
    if not os.path.exists(RANGE_HISTORY_PATH):
        return []
    try:
        with open(RANGE_HISTORY_PATH, 'r', encoding='utf-8') as f:
            data = json.load(f)
            if not isinstance(data, list):
                return []
            result = []
            for item in data:
                if not isinstance(item, dict):
                    continue
                f_ts = int(item.get('from', 0))
                t_ts = int(item.get('to', 0))
                if f_ts and t_ts and f_ts < t_ts:
                    label = item.get('label') or '{:%Y-%m-%d %H:%M:%S} ~ {:%Y-%m-%d %H:%M:%S}'.format(
                        datetime.fromtimestamp(f_ts), datetime.fromtimestamp(t_ts)
                    )
                    result.append({'from': f_ts, 'to': t_ts, 'label': label})
            return result[:RANGE_HISTORY_MAX]
    except Exception:
        return []


def save_range_history(history):
    try:
        with open(RANGE_HISTORY_PATH, 'w', encoding='utf-8') as f:
            json.dump(history[:RANGE_HISTORY_MAX], f, ensure_ascii=False, indent=2)
    except Exception as e:
        print('保存时间区间历史失败: {}'.format(e))


def push_range_history(history, from_ts, to_ts):
    if not from_ts or not to_ts or from_ts >= to_ts:
        return history
    label = '{:%Y-%m-%d %H:%M:%S} ~ {:%Y-%m-%d %H:%M:%S}'.format(
        datetime.fromtimestamp(from_ts), datetime.fromtimestamp(to_ts)
    )
    history = [h for h in history if not (h['from'] == from_ts and h['to'] == to_ts)]
    history.insert(0, {'from': from_ts, 'to': to_ts, 'label': label})
    return history[:RANGE_HISTORY_MAX]


def parse_logstores(raw):
    if isinstance(raw, str):
        return [raw] if raw.strip() else []
    if isinstance(raw, list):
        return [str(x) for x in raw if str(x).strip()]
    return []


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
        self._pending_page = None
        self.history = load_history()
        self.range_history = load_range_history()

        self.logstores = parse_logstores(config.get('logstore'))
        if not self.logstores:
            raise ValueError('配置中未找到 logstore，请检查 .config.json')
        self.logstore = self.logstores[0]

        self.setWindowTitle('SLS 日志查看器  -  {}/{}'.format(
            config.get('project', ''), self.logstore
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

        bar.addWidget(QLabel('日志库:'))
        self.logstore_combo = QComboBox()
        self.logstore_combo.addItems(self.logstores)
        if len(self.logstores) <= 1:
            self.logstore_combo.setEnabled(False)
        self.logstore_combo.currentTextChanged.connect(self.on_logstore_changed)
        bar.addWidget(self.logstore_combo)

        bar.addSpacing(4)
        bar.addWidget(QLabel('时间:'))
        self.time_combo = QComboBox()
        for label, _ in TIME_PRESETS:
            self.time_combo.addItem(label)
        self.time_combo.addItem('自定义...')
        self.time_combo.setCurrentIndex(1)
        self.time_combo.currentIndexChanged.connect(self.on_time_mode_change)
        bar.addWidget(self.time_combo)

        bar.addSpacing(8)
        bar.addWidget(QLabel('历史:'))
        self.range_history_combo = QComboBox()
        self.range_history_combo.setMinimumWidth(220)
        self.range_history_combo.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.range_history_combo.addItem('— 选择历史时间区间 —')
        for item in self.range_history:
            self.range_history_combo.addItem(item['label'], item)
        self.range_history_combo.activated.connect(self.on_range_history_activated)
        self.range_history_combo.setEnabled(bool(self.range_history))
        bar.addWidget(self.range_history_combo)

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

        history_row = QHBoxLayout()
        history_row.addStretch()
        self.clear_history_btn = QPushButton('清空搜索/区间历史')
        self.clear_history_btn.clicked.connect(self.on_clear_history)
        history_row.addWidget(self.clear_history_btn)
        layout.addLayout(history_row)

        splitter = QSplitter(Qt.Vertical)

        self.table = QTableWidget()
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(['时间', '主机', '内容'])
        self.table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeToContents
        )
        self.table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeToContents
        )
        self.table.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.Stretch
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
        self.detail.setLineWrapMode(QPlainTextEdit.NoWrap)
        self.detail.setFont(QFont('Consolas', 10))
        self.detail.setPlaceholderText('选中上面表格中的一行以查看完整 JSON（所有字段）')
        splitter.addWidget(self.detail)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)

        layout.addWidget(splitter, 1)

        pager = QHBoxLayout()
        self.first_btn = QPushButton('<< 首页')
        self.first_btn.clicked.connect(self.on_first)
        pager.addWidget(self.first_btn)

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

        self.last_btn = QPushButton('末页 >>')
        self.last_btn.clicked.connect(self.on_last)
        pager.addWidget(self.last_btn)

        pager.addStretch()

        pager.addWidget(QLabel('跳转:'))
        self.page_spin = QSpinBox()
        self.page_spin.setMinimum(1)
        self.page_spin.setMaximum(1)
        self.page_spin.setValue(1)
        self.page_spin.setFixedWidth(60)
        self.page_spin.valueChanged.connect(self.on_page_jump)
        pager.addWidget(self.page_spin)
        self.total_pages_label = QLabel('/ 1')
        pager.addWidget(self.total_pages_label)

        pager.addSpacing(8)
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

    def on_logstore_changed(self, name):
        if not name or name == self.logstore:
            return
        self.logstore = name
        self.current_page = 0
        self._pending_page = None
        self.total_count = 0
        self._update_pagination_labels()
        self.setWindowTitle('SLS 日志查看器  -  {}/{}'.format(
            self.config.get('project', ''), self.logstore
        ))
        if self.worker and self.worker.isRunning():
            return
        self._run_query()

    def on_search(self):
        if self.worker and self.worker.isRunning():
            return
        query = self.query_combo.currentText().strip()
        self._record_history(query)
        self.current_page = 0
        self._pending_page = None
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

    def _record_range_history(self, from_ts, to_ts):
        if not from_ts or not to_ts or from_ts >= to_ts:
            return
        before_len = len(self.range_history)
        self.range_history = push_range_history(self.range_history, from_ts, to_ts)
        if len(self.range_history) != before_len:
            save_range_history(self.range_history)
            self.range_history_combo.blockSignals(True)
            self.range_history_combo.clear()
            self.range_history_combo.addItem('— 选择历史时间区间 —')
            for item in self.range_history:
                self.range_history_combo.addItem(item['label'], item)
            self.range_history_combo.setEnabled(True)
            self.range_history_combo.blockSignals(False)

    def _rotate_log_if_needed(self):
        try:
            if os.path.exists(LOG_PATH) and os.path.getsize(LOG_PATH) > LOG_MAX_BYTES:
                backup = LOG_PATH + '.1'
                if os.path.exists(backup):
                    os.remove(backup)
                os.replace(LOG_PATH, backup)
        except Exception:
            pass

    def _write_log_file(self, query, logs):
        try:
            self._rotate_log_if_needed()
            with open(LOG_PATH, 'a', encoding='utf-8') as f:
                ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                f.write('===== [{}] query={!r} range={} page={} =====\n'.format(
                    ts, query, self.format_range_label(),
                    self.current_page + 1
                ))
                for entry in logs:
                    contents = dict(entry.contents)
                    f.write(json.dumps(
                        contents, ensure_ascii=False, sort_keys=True
                    ))
                    f.write('\n')
                f.write('\n')
        except Exception as e:
            self.statusBar().showMessage(
                '写入日志失败: {}'.format(e), 5000
            )

    def on_prev(self):
        if self.worker and self.worker.isRunning():
            return
        if self.current_page > 0:
            self.current_page -= 1
            self._pending_page = None
            self._run_query()

    def on_next(self):
        if self.worker and self.worker.isRunning():
            return
        self._pending_page = self.current_page + 1
        self._run_query()

    def on_first(self):
        if self.worker and self.worker.isRunning():
            return
        if self.current_page > 0:
            self.current_page = 0
            self._pending_page = None
            self._run_query()

    def on_last(self):
        if self.worker and self.worker.isRunning():
            return
        last_page = max(0, (self.total_count - 1) // self.page_size)
        if self.total_count > 0 and self.current_page < last_page:
            self.current_page = last_page
            self._pending_page = None
            self._run_query()

    def on_page_jump(self, page_num):
        if self.worker and self.worker.isRunning():
            return
        page_idx = page_num - 1
        if page_idx == self.current_page:
            return
        last_page = max(0, (self.total_count - 1) // self.page_size)
        if self.total_count > 0 and page_idx > last_page:
            page_idx = last_page
        self._pending_page = page_idx
        self._run_query()

    def on_page_size_change(self):
        self.page_size = int(self.page_size_combo.currentText())
        self.current_page = 0
        self._pending_page = None
        if self.worker and self.worker.isRunning():
            return
        self._run_query()

    def on_row_selected(self):
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return
        row = rows[0].row()
        item = self.table.item(row, 0)
        if not item:
            return
        json_text = item.data(Qt.UserRole)
        if not json_text:
            content_item = self.table.item(row, 1)
            json_text = content_item.text() if content_item else ''
        self.detail.setPlainText(json_text)

    def on_clear_history(self):
        if not self.history and not self.range_history:
            self.statusBar().showMessage('历史已为空', 3000)
            return
        reply = QMessageBox.question(
            self, '清空历史', '确定要清空所有搜索历史与时间区间历史吗？',
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return
        self.history = []
        self.range_history = []
        save_history(self.history)
        save_range_history(self.range_history)
        self.query_combo.clear()
        self.query_combo.lineEdit().setPlaceholderText(
            '输入 SLS 查询语句（例: _doRandomTeleporter 或 level:ERROR），回车搜索；'
            '下拉框显示历史搜索'
        )
        self.range_history_combo.blockSignals(True)
        self.range_history_combo.clear()
        self.range_history_combo.addItem('— 选择历史时间区间 —')
        self.range_history_combo.setEnabled(False)
        self.range_history_combo.blockSignals(False)
        self.statusBar().showMessage('历史已清空', 3000)

    def on_range_history_activated(self, index):
        if index <= 0:
            return
        item = self.range_history_combo.itemData(index)
        if not item:
            return
        from_ts = int(item.get('from', 0))
        to_ts = int(item.get('to', 0))
        if not from_ts or not to_ts:
            return
        self.time_combo.setCurrentIndex(CUSTOM_RANGE_INDEX)
        self.from_dt.setDateTime(QDateTime.fromSecsSinceEpoch(from_ts))
        self.to_dt.setDateTime(QDateTime.fromSecsSinceEpoch(to_ts))
        self.range_history_combo.setCurrentIndex(0)
        self.on_apply_range()

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
            host_item = self.table.item(idx, 1)
            content_item = self.table.item(idx, 2)
            ts = ts_item.text() if ts_item else ''
            host = host_item.text() if host_item else ''
            content = content_item.text() if content_item else ''
            parts = [ts, host, content]
            lines.append('\t'.join(p for p in parts if p))
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
            host_item = self.table.item(i, 1)
            content_item = self.table.item(i, 2)
            ts = ts_item.text() if ts_item else ''
            host = host_item.text() if host_item else ''
            content = content_item.text() if content_item else ''
            parts = [ts, host, content]
            lines.append('\t'.join(p for p in parts if p))
        QApplication.clipboard().setText('\n'.join(lines))
        self.statusBar().showMessage(
            '已复制当前页 {} 行到剪贴板'.format(self.table.rowCount()), 3000
        )

    def _run_query(self):
        query = self.query_combo.currentText().strip()
        from_time, to_time = self.get_time_range()
        self._record_range_history(from_time, to_time)
        offset_page = self._pending_page if self._pending_page is not None else self.current_page
        offset = offset_page * self.page_size

        self.statusBar().showMessage('查询中... [{}]'.format(self.format_range_label()))
        self.search_btn.setEnabled(False)
        self.prev_btn.setEnabled(False)
        self.next_btn.setEnabled(False)
        self.table.setRowCount(0)
        self.detail.clear()

        self.worker = QueryWorker(
            self.client,
            self.config['project'],
            self.logstore,
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
        pending = self._pending_page
        self._pending_page = None

        if pending is not None and len(logs) == 0:
            self.table.setRowCount(0)
            self.detail.clear()
            self._update_pagination_labels()
            self.search_btn.setEnabled(True)
            self.statusBar().showMessage(
                '第 {} 页无数据，已保持在第 {} 页（共 {} 条）'.format(
                    pending + 1, self.current_page + 1, self.total_count
                ), 5000
            )
            return

        if pending is not None:
            self.current_page = pending

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

            hostname = (
                contents.get('__tag__:__hostname__', '')
                or contents.get('__tag__:__host__', '')
                or getattr(log, 'source', '')
            )

            json_text = json.dumps(
                contents, ensure_ascii=False, indent=2, sort_keys=True
            )

            ts_item = QTableWidgetItem(ts_text)
            ts_item.setData(Qt.UserRole, json_text)
            self.table.setItem(i, 0, ts_item)
            self.table.setItem(i, 1, QTableWidgetItem(hostname))
            self.table.setItem(i, 2, QTableWidgetItem(content_str))

        self._update_pagination_labels()

        self.search_btn.setEnabled(True)
        self._write_log_file(self.query_combo.currentText().strip(), logs)
        self.statusBar().showMessage(
            '查询完成: 当前页 {} 条，总计 {} 条；日志已追加到 {}'.format(
                len(logs), total, os.path.basename(LOG_PATH)
            )
        )

    def on_query_error(self, msg):
        self._pending_page = None
        self.search_btn.setEnabled(True)
        self.total_count = 0
        self._update_pagination_labels()
        self.statusBar().showMessage('查询失败: {}'.format(msg))
        QMessageBox.critical(self, '查询失败', msg)

    def _update_pagination_labels(self):
        if self.total_count == 0:
            total_pages = 1
        else:
            total_pages = max(1, (self.total_count + self.page_size - 1) // self.page_size)
        self.page_label.setText(
            '第 {} / {} 页'.format(self.current_page + 1, total_pages)
        )
        self.total_label.setText('共 {} 条'.format(self.total_count))
        self.total_pages_label.setText('/ {}'.format(total_pages))

        self.page_spin.blockSignals(True)
        self.page_spin.setMaximum(max(1, total_pages))
        self.page_spin.setValue(self.current_page + 1)
        self.page_spin.blockSignals(False)

        has_prev = self.current_page > 0
        has_more = (self.current_page + 1) * self.page_size < self.total_count
        self.first_btn.setEnabled(has_prev)
        self.prev_btn.setEnabled(has_prev)
        self.next_btn.setEnabled(True)
        self.last_btn.setEnabled(
            has_more and self.total_count > 0
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