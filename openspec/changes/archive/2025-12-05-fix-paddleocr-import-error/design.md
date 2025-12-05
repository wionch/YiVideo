# 修复 paddleocr_service 导入错误 - 技术设计

## 技术方案

### 当前状态分析

**问题文件**: `services/workers/paddleocr_service/app/modules/decoder.py`
**错误行**: 第10行
```python
from ..utils.progress_logger import create_progress_bar
```

**问题**:
1. 使用相对导入 `..utils.progress_logger` 指向 `services/workers/paddleocr_service/app/utils/progress_logger.py`
2. 该模块已被删除（从 git status 可看到状态为 D）
3. 在 `decoder.py` 中，`create_progress_bar` 用于创建解码进度条（第62行和第245行）

**现有资源**:
- `services/common/progress_logger.py` 包含完整的进度条实现
- 第186行定义了 `create_progress_bar` 函数
- 第191行定义了 `create_stage_progress` 函数
- 这些函数与 decoder.py 需要的接口兼容

### 解决方案

**修改方案**: 将相对导入改为绝对导入

**修改前**:
```python
from ..utils.progress_logger import create_progress_bar
```

**修改后**:
```python
from services.common.progress_logger import create_progress_bar
```

### 技术细节

**为什么这样修改**:
1. **一致性**: `area_detector.py` 已经使用相同的导入方式（第24行）
2. **可维护性**: 所有服务共享 common 中的通用模块
3. **功能完整性**: `services.common.progress_logger` 提供完整的功能集
4. **向后兼容**: 修复不改变任何功能，仅修正导入路径

**代码兼容性**:
- `decoder.py` 中使用 `create_progress_bar` 的方式无需改变
- 函数接口保持完全一致
- ProgressBar 类的方法签名不变

### 验证策略

**单元验证**:
- 确认修改后的文件语法正确
- 验证 Python 模块加载无错误

**集成验证**:
- 运行完整的 detect_subtitle_area 工作流
- 确认进度条正常显示和工作

### 风险评估

**风险**: 极低
**原因**:
1. 只修改一个导入语句
2. 不改变任何业务逻辑
3. 不影响其他模块或服务
4. 容易回滚

**测试覆盖**:
- 模块导入测试
- 功能集成测试
- 回归测试（确保其他功能未受影响）

### 替代方案

**方案1** (采用): 修改导入路径到 services.common.progress_logger
- 优点: 简单直接，与现有代码一致
- 缺点: 无

**方案2** (不考虑): 恢复已删除的 utils/progress_logger.py
- 优点: 保持原有导入方式
- 缺点: 引入重复代码，违背 DRY 原则

**方案3** (不考虑): 创建符号链接
- 优点: 无需修改代码
- 缺点: 跨服务目录创建链接不现实

### 实施步骤

1. 修改 decoder.py 第10行导入语句
2. 保存文件
3. 运行导入测试
4. 执行完整功能测试
5. 验证无副作用

### 预期结果

**成功指标**:
- decoder.py 成功导入
- paddleocr.detect_subtitle_area 任务完成
- 无 ModuleNotFoundError
- 进度条正常工作

**性能影响**:
- 无性能影响
- 导入路径变化不影响运行时性能
