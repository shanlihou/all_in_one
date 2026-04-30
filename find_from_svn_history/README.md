# SVN历史关键字搜索工具

从SVN历史版本的diff中搜索包含指定关键字的代码。

## 环境要求

- Python 3.x
- Windows SVN命令行工具（svn命令可用）

## 配置

首次运行会自动生成 `config.json` 配置文件：

```json
{
    "keyword": "TODO",
    "max_versions": 50,
    "svn_path": ""
}
```

编辑配置文件后运行：

```bash
python find_from_svn_history.py
```

### 配置项说明

- `keyword`：要搜索的关键字
- `max_versions`：最多搜索的历史版本数量
- `svn_path`：SVN工作目录路径，留空则使用当前目录

## 示例

1. 编辑 `config.json`：
```json
{
    "keyword": "TODO",
    "max_versions": 100,
    "svn_path": "F:\\project"
}
```

2. 运行脚本：
```bash
python find_from_svn_history.py
```

## 工作原理

1. 执行`svn log`获取历史版本列表
2. 对每个版本执行`svn diff`对比前一个版本
3. 在diff输出中搜索关键字
4. 输出包含匹配的版本信息（版本号、作者、日期、提交信息）

## 注意事项

- 需在SVN工作目录或指定有效路径运行
- 搜索大量版本时可能较慢
- 仅显示diff中添加/修改的行（不包含删除行中的匹配）
