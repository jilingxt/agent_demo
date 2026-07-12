from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from time import sleep

import openpyxl


ROOT = Path(__file__).resolve().parents[1]
GENERATOR = ROOT / "scripts" / "generate_bayesian_statistics_workbook.py"
WORKBOOK = ROOT / "docs" / "statistics" / "bayesian_parameter_collection_template.xlsx"
SHEETS = [
    "填写说明",
    "参数需求清单",
    "原子事实核验",
    "来源观测统计",
    "抽取准确率",
    "来源依赖",
    "案件族CPD",
    "权威锚定复核",
    "模型发布记录",
    "枚举值",
]
REQUIRED_HEADERS = {
    "参数需求清单": {"参数类别", "参数名称", "是否需真实数据", "所需统计量", "法律边界"},
    "原子事实核验": {"样本ID", "模型输出标签", "独立核验标签", "统计分类"},
    "来源观测统计": {"TP", "FP", "FN", "TN", "未知数", "后验均值"},
    "抽取准确率": {"TP", "FP", "FN", "TN", "精确率", "召回率"},
    "来源依赖": {"来源A类别", "来源B类别", "共同来源标识", "依赖复核结论"},
    "案件族CPD": {"模型ID", "父节点状态", "先验Alpha", "后验均值"},
    "权威锚定复核": {"权威来源ID", "有效性状态", "适用范围复核"},
    "模型发布记录": {"模型ID", "参数哈希", "离线审批状态", "隐私检查"},
}


def _load_generator():
    spec = spec_from_file_location("statistics_workbook_generator", GENERATOR)
    assert spec and spec.loader
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _headers(sheet):
    return {cell.value for cell in sheet[1] if cell.value}


def test_generator_creates_the_governed_workbook_contract(tmp_path):
    assert GENERATOR.exists()
    generated = tmp_path / WORKBOOK.name
    _load_generator().build_workbook(generated)

    workbook = openpyxl.load_workbook(generated, data_only=False)

    assert workbook.sheetnames == SHEETS
    for sheet in workbook.worksheets:
        assert sheet.freeze_panes == "A2"
        assert sheet.auto_filter.ref
        assert sheet.sheet_view.showGridLines is False

    for sheet_name, expected_headers in REQUIRED_HEADERS.items():
        assert expected_headers <= _headers(workbook[sheet_name])

    formulas = [
        cell.value
        for sheet in workbook.worksheets
        for row in sheet.iter_rows()
        for cell in row
        if cell.data_type == "f"
    ]
    assert any("未知" in formula and '=""' in formula for formula in formulas)
    assert any("Alpha" not in formula and "/" in formula for formula in formulas)

    validations = [
        validation
        for sheet in workbook.worksheets
        for validation in sheet.data_validations.dataValidation
    ]
    assert validations
    assert all(validation.type == "list" for validation in validations)
    assert {"=LabelValues", "=ApprovalValues", "=PrivacyValues", "=YesNoDataValues"} <= {
        validation.formula1 for validation in validations
    }


def test_checked_in_workbook_matches_the_contract():
    assert WORKBOOK.exists()
    workbook = openpyxl.load_workbook(WORKBOOK, data_only=False)
    assert workbook.sheetnames == SHEETS
    assert all(sheet.freeze_panes == "A2" for sheet in workbook.worksheets)


def test_generator_output_is_byte_reproducible(tmp_path):
    output = tmp_path / WORKBOOK.name
    generator = _load_generator()

    generator.build_workbook(output)
    first = output.read_bytes()
    sleep(2.1)
    generator.build_workbook(output)

    assert output.read_bytes() == first
