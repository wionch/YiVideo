# 设计文档：工作流节点文档功能一致性检查

## 变化 ID

check-workflow-nodes-documentation-consistency

## 设计目标

通过系统化的代码分析、文档检查和一致性验证，确保 YiVideo 系统的工作流节点文档与实际代码实现保持完全同步，提升文档的准确性和可用性。

## 核心设计理念

### 1. 渐进式验证

采用分阶段的验证方法，从文档结构分析到具体的参数对比，逐步深入验证每个层面的一致性。

### 2. 自动化辅助

使用代码搜索和文本分析工具辅助人工检查，提高检查效率和准确性。

### 3. 全方位覆盖

检查覆盖功能描述、参数定义、输出格式、依赖关系、使用示例等文档的各个重要方面。

### 4. 变更可追溯

建立问题追踪机制，记录发现的每个不一致问题及其修复状态。

## 详细设计

### 阶段 1: 代码分析架构

#### 1.1 文档解析模块

```python
class DocumentationParser:
    def __init__(self, doc_path: str):
        self.doc_path = doc_path
        self.parsed_structure = {}

    def parse_nodes(self) -> List[WorkflowNode]:
        """解析文档中的所有工作流节点"""
        # 提取节点名称、参数、输出格式等信息

    def extract_parameter_definitions(self, node_section: str) -> Dict[str, Any]:
        """从节点文档中提取参数定义"""
        # 使用正则表达式或markdown解析

    def extract_output_format(self, node_section: str) -> Dict[str, Any]:
        """从节点文档中提取输出格式定义"""
        # 解析JSON格式的输出示例
```

#### 1.2 代码分析模块

```python
class CodeAnalyzer:
    def __init__(self):
        self.service_dirs = [
            "services/workers/ffmpeg_service",
            "services/workers/faster_whisper_service",
            "services/workers/audio_separator_service",
            "services/workers/pyannote_audio_service",
            "services/workers/paddleocr_service",
            "services/workers/indextts_service",
            "services/workers/wservice"
        ]

    def analyze_task_parameters(self, task_file: str) -> Dict[str, Any]:
        """分析任务文件的参数定义"""
        # 使用AST解析或正则表达式提取参数

    def analyze_output_structure(self, task_function: callable) -> Dict[str, Any]:
        """分析任务函数的输出结构"""
        # 通过代码分析和实际运行分析输出
```

### 阶段 2: 一致性检查算法

#### 2.1 参数一致性检查算法

```python
def check_parameter_consistency(doc_params: Dict, code_params: Dict) -> ConsistencyResult:
    """
    检查参数一致性

    比较维度：
    1. 参数名称是否完全匹配
    2. 参数类型是否一致
    3. 默认值是否匹配
    4. 是否存在额外参数
    5. 是否存在缺失参数
    """
    result = ConsistencyResult()

    # 检查参数名称匹配
    doc_param_names = set(doc_params.keys())
    code_param_names = set(code_params.keys())

    result.missing_in_doc = code_param_names - doc_param_names
    result.extra_in_doc = doc_param_names - code_param_names

    # 检查参数类型和默认值
    for param_name in doc_param_names & code_param_names:
        doc_param = doc_params[param_name]
        code_param = code_params[param_name]

        if not param_type_matches(doc_param, code_param):
            result.type_mismatches[param_name] = (doc_param, code_param)

        if not default_value_matches(doc_param, code_param):
            result.default_mismatches[param_name] = (doc_param, code_param)

    return result
```

#### 2.2 输出格式一致性检查算法

```python
def check_output_consistency(doc_output: Dict, code_output: Dict) -> OutputConsistencyResult:
    """
    检查输出格式一致性
    """
    result = OutputConsistencyResult()

    # 检查输出字段
    doc_output_fields = extract_output_fields(doc_output)
    code_output_fields = extract_output_fields(code_output)

    result.missing_fields = code_output_fields - doc_output_fields
    result.extra_fields = doc_output_fields - code_output_fields

    # 检查字段类型
    for field in doc_output_fields & code_output_fields:
        if not field_type_consistent(field, doc_output, code_output):
            result.field_type_issues[field] = "类型不匹配"

    return result
```

#### 2.3 依赖关系验证算法

```python
def validate_dependency_relationships(nodes: List[WorkflowNode]) -> DependencyValidationResult:
    """
    验证工作流节点依赖关系
    """
    result = DependencyValidationResult()

    # 构建依赖图
    dependency_graph = build_dependency_graph(nodes)

    # 检查循环依赖
    cycles = detect_cycles(dependency_graph)
    if cycles:
        result.circular_dependencies = cycles

    # 检查依赖完整性
    for node in nodes:
        missing_deps = check_missing_dependencies(node, dependency_graph)
        if missing_deps:
            result.incomplete_dependencies[node.name] = missing_deps

    return result
```

### 阶段 3: 自动化检查流程

#### 3.1 分层检查策略

```python
class ConsistencyChecker:
    def __init__(self):
        self.checkers = [
            self.check_parameter_consistency,
            self.check_output_consistency,
            self.check_dependency_consistency,
            self.check_example_validity,
            self.check_functional_logic
        ]

    def run_consistency_check(self) -> ConsistencyReport:
        """运行全面的一致性检查"""
        report = ConsistencyReport()

        for checker in self.checkers:
            try:
                check_result = checker()
                report.add_result(checker.__name__, check_result)
            except Exception as e:
                report.add_error(checker.__name__, str(e))

        return report
```

#### 3.2 交叉验证机制

```python
def cross_validate_nodes(nodes: List[WorkflowNode]) -> CrossValidationResult:
    """
    交叉验证节点间的一致性
    """
    result = CrossValidationResult()

    # 验证输入输出匹配
    for source_node in nodes:
        for target_node in nodes:
            if source_node.output_refs_target(target_node):
                validation = validate_io_compatibility(source_node, target_node)
                result.add_validation_result(source_node.name, target_node.name, validation)

    return result
```

### 阶段 4: 问题分类和优先级

#### 4.1 问题分类体系

```python
class InconsistencyType(Enum):
    # 参数相关
    PARAMETER_MISSING = "parameter_missing"
    PARAMETER_EXTRA = "parameter_extra"
    PARAMETER_TYPE_MISMATCH = "parameter_type_mismatch"
    PARAMETER_DEFAULT_MISMATCH = "parameter_default_mismatch"

    # 输出相关
    OUTPUT_FIELD_MISSING = "output_field_missing"
    OUTPUT_FIELD_EXTRA = "output_field_extra"
    OUTPUT_TYPE_MISMATCH = "output_type_mismatch"

    # 逻辑相关
    FUNCTIONAL_DESCRIPTION_MISMATCH = "functional_description_mismatch"
    DEPENDENCY_INCONSISTENCY = "dependency_inconsistency"
    LOGIC_FLOW_ERROR = "logic_flow_error"

    # 示例相关
    EXAMPLE_OUTDATED = "example_outdated"
    EXAMPLE_INVALID = "example_invalid"
    EXAMPLE_MISSING = "example_missing"
```

#### 4.2 优先级评估

```python
def assess_issue_priority(issue: ConsistencyIssue) -> IssuePriority:
    """
    评估问题优先级
    """
    priority_factors = {
        'impact': calculate_impact_score(issue),  # 对系统功能的影响
        'frequency': calculate_frequency_score(issue),  # 问题发生的频率
        'severity': calculate_severity_score(issue),  # 严重程度
        'fix_complexity': calculate_fix_complexity(issue)  # 修复复杂度
    }

    # 使用加权评分计算优先级
    priority_score = (
        priority_factors['impact'] * 0.4 +
        priority_factors['frequency'] * 0.3 +
        priority_factors['severity'] * 0.2 +
        priority_factors['fix_complexity'] * 0.1
    )

    return determine_priority_level(priority_score)
```

### 阶段 5: 修复策略设计

#### 5.1 自动修复类型

```python
class AutoFixType(Enum):
    # 简单参数同步
    PARAMETER_SYNC = "parameter_sync"

    # 文档格式调整
    FORMAT_FIX = "format_fix"

    # 缺失信息补充
    INFO_ADDITION = "info_addition"

    # 格式标准化
    STANDARDIZATION = "standardization"
```

#### 5.2 修复验证机制

```python
class FixValidator:
    def __init__(self):
        self.validation_rules = [
            self.validate_syntax,
            self.validate_format,
            self.validate_completeness,
            self.validate_consistency
        ]

    def validate_fix(self, original_doc: str, fixed_doc: str) -> FixValidationResult:
        """
        验证修复后的文档
        """
        result = FixValidationResult()

        for rule in self.validation_rules:
            validation_result = rule(original_doc, fixed_doc)
            result.add_rule_result(rule.__name__, validation_result)

        return result
```

## 技术实现方案

### 1. 工具选择

-   **文档解析**: 使用 markdown 解析库或自定义正则表达式
-   **代码分析**: 使用 AST（抽象语法树）分析 Python 代码
-   **比较算法**: 使用文本相似度算法进行差异检测
-   **验证工具**: 集成代码执行环境进行功能验证

### 2. 性能优化

-   **缓存机制**: 缓存已解析的文档和代码结构
-   **并行处理**: 对不同服务的检查并行执行
-   **增量检查**: 只检查修改过的节点和文档部分
-   **批量操作**: 批量处理相似类型的不一致问题

### 3. 扩展性设计

-   **插件架构**: 支持添加新的检查规则和修复策略
-   **配置化**: 通过配置文件自定义检查范围和标准
-   **版本控制**: 集成版本控制，跟踪文档和代码的变更历史
-   **报告系统**: 生成多种格式的检查报告（HTML、PDF、JSON 等）

## 质量保证

### 1. 测试策略

-   **单元测试**: 对每个检查模块进行单元测试
-   **集成测试**: 测试整个检查流程的完整性
-   **回归测试**: 确保检查不会影响现有功能
-   **性能测试**: 验证检查工具的性能和扩展性

### 2. 验证方法

-   **模拟数据测试**: 使用模拟的不一致数据进行测试
-   **真实案例验证**: 使用实际的项目代码进行验证
-   **同行评审**: 对检查结果进行人工评审
-   **持续改进**: 基于反馈不断优化检查算法

## 风险缓解

### 1. 技术风险

-   **复杂性管理**: 分阶段实施，逐步增加复杂度
-   **性能风险**: 预定义性能基准，监控执行时间
-   **准确性风险**: 人工验证关键检查结果
-   **兼容性风险**: 确保工具兼容不同版本的代码

### 2. 业务风险

-   **文档停用风险**: 制定回滚计划，确保文档始终可用
-   **开发效率影响**: 优化工具性能，减少对开发流程的影响
-   **维护负担**: 建立自动化机制，减少人工维护工作

---

**设计版本**: 1.0
**创建时间**: 2025-12-02T05:36:00Z
**设计者**: Kilo Code Architect Mode
