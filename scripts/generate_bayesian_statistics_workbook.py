from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from xml.etree import ElementTree
from zipfile import ZIP_DEFLATED, ZipFile

from openpyxl import Workbook
from openpyxl.formatting.rule import FormulaRule
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter, quote_sheetname
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.workbook.defined_name import DefinedName


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = (
    ROOT / "docs" / "statistics" / "bayesian_parameter_collection_template.xlsx"
)
MAX_DATA_ROW = 501

SHEET_ROWS = {
    "填写说明": [
        ["主题", "要求", "示例/备注"],
        ["数据边界", "仅收集去标识化统计，不录入姓名、证件号、联系方式或材料原文。", "样本ID使用不可逆内部代号。"],
        ["标签", "独立核验标签仅可为真、假、未知；空白表示尚未核验。", "未知不得折算为假。"],
        ["混淆矩阵", "TP/FP/FN/TN仅由模型输出标签与独立核验标签均为真或假时生成。", "未知和空白不进入分母。"],
        ["Beta后验", "后验Alpha=先验Alpha+成功数；后验Beta=先验Beta+失败数。", "后验均值=后验Alpha/(后验Alpha+后验Beta)。"],
        ["独立核验", "核验人不得直接沿用模型输出；分歧须由另一角色裁决。", "记录角色代号，不记录姓名。"],
        ["来源与依赖", "记录数据批次、来源类别及共同来源，避免把复制材料当作独立观察。", "不得粘贴证据全文。"],
        ["离线发布", "参数包须经独立复核、隐私检查和离线审批后发布。", "记录模型版本、参数哈希和替代关系。"],
        ["法律边界", "法定年龄、数额、次数、身份、权限、抗辩、例外和适用范围不得由统计学习。", "这些值由法律规则或经批准的专家先验管理。"],
    ],
    "原子事实核验": [[
        "样本ID", "案件族", "原子事实ID", "谓词", "模型输出标签", "独立核验标签",
        "统计分类", "核验人代号", "核验日期", "分歧处理状态", "数据来源批次", "备注",
    ]],
    "来源观测统计": [[
        "模型ID", "模型版本", "谓词", "来源类别", "指标类型", "TP", "FP", "FN", "TN",
        "未知数", "先验Alpha", "先验Beta", "后验Alpha", "后验Beta", "后验均值", "数据批次", "备注",
    ]],
    "抽取准确率": [[
        "抽取器ID", "版本", "字段/谓词", "数据批次", "TP", "FP", "FN", "TN", "未知数",
        "精确率", "召回率", "F1", "备注",
    ]],
    "来源依赖": [[
        "依赖记录ID", "数据批次", "来源A类别", "来源B类别", "共同来源标识", "共同制作过程",
        "时间/内容耦合说明", "依赖复核结论", "复核人代号", "复核日期", "备注",
    ]],
    "案件族CPD": [[
        "模型ID", "模型版本", "案件族", "子节点", "父节点状态", "子节点真计数", "子节点假计数",
        "未知数", "先验Alpha", "先验Beta", "后验Alpha", "后验Beta", "后验均值", "数据批次", "备注",
    ]],
    "权威锚定复核": [[
        "权威来源ID", "文书类型", "版本/发布日期", "来源位置", "有效性状态", "适用范围复核",
        "独立复核状态", "复核人代号", "复核日期", "失效/替代说明", "备注",
    ]],
    "模型发布记录": [[
        "模型ID", "模型版本", "参数哈希", "校准状态", "数据截止日期", "数据批次", "独立复核状态",
        "离线审批状态", "审批角色代号", "审批日期", "隐私检查", "发布包相对路径", "替代版本", "备注",
    ]],
}

ENUMS = {
    "LabelValues": ("标签值", ["真", "假", "未知"]),
    "CaseFamilyValues": ("案件族", ["conduct_result", "property_taking", "public_order", "public_safety", "status_duty"]),
    "ObservationMetricValues": ("观测指标", ["真阳性率", "假阳性率"]),
    "YesNoUnknownValues": ("是/否/未知", ["是", "否", "未知"]),
    "DependencyValues": ("依赖复核", ["独立", "可能依赖", "确认依赖", "未知"]),
    "ReviewValues": ("核验状态", ["未开始", "待复核", "一致", "已裁决"]),
    "ValidityValues": ("有效性", ["有效", "待核验", "已失效", "未知"]),
    "ScopeValues": ("适用范围", ["符合", "不符合", "待法律复核"]),
    "CalibrationValues": ("校准状态", ["expert_prior_unvalidated", "pilot_uncalibrated", "validated"]),
    "ApprovalValues": ("审批状态", ["草稿", "待审批", "已批准", "已拒绝"]),
    "PrivacyValues": ("隐私检查", ["未完成", "通过", "不通过"]),
}

VALIDATIONS = {
    "原子事实核验": {"B": "CaseFamilyValues", "E": "LabelValues", "F": "LabelValues", "J": "ReviewValues"},
    "来源观测统计": {"E": "ObservationMetricValues"},
    "来源依赖": {"E": "YesNoUnknownValues", "F": "YesNoUnknownValues", "H": "DependencyValues"},
    "案件族CPD": {"C": "CaseFamilyValues"},
    "权威锚定复核": {"E": "ValidityValues", "F": "ScopeValues", "G": "ReviewValues"},
    "模型发布记录": {"D": "CalibrationValues", "G": "ReviewValues", "H": "ApprovalValues", "K": "PrivacyValues"},
}

FORMULAS = {
    "原子事实核验": {
        "G2": '=IF(OR(E2="",F2=""),"",IF(OR(E2="未知",F2="未知"),"未知",IF(AND(E2="真",F2="真"),"TP",IF(AND(E2="真",F2="假"),"FP",IF(AND(E2="假",F2="真"),"FN","TN")))))',
    },
    "来源观测统计": {
        "M2": '=IF(E2="真阳性率",K2+F2,IF(E2="假阳性率",K2+G2,""))',
        "N2": '=IF(E2="真阳性率",L2+H2,IF(E2="假阳性率",L2+I2,""))',
        "O2": '=IF(OR(M2="",N2="",M2+N2=0),"",M2/(M2+N2))',
    },
    "抽取准确率": {
        "J2": '=IF(E2+F2=0,"",E2/(E2+F2))',
        "K2": '=IF(E2+G2=0,"",E2/(E2+G2))',
        "L2": '=IF(OR(J2="",K2="",J2+K2=0),"",2*J2*K2/(J2+K2))',
    },
    "案件族CPD": {
        "K2": '=IF(OR(I2="",F2=""),"",I2+F2)',
        "L2": '=IF(OR(J2="",G2=""),"",J2+G2)',
        "M2": '=IF(OR(K2="",L2="",K2+L2=0),"",K2/(K2+L2))',
    },
}

HEADER_FILL = PatternFill("solid", fgColor="1F4E5F")
FORMULA_FILL = PatternFill("solid", fgColor="E8F1F4")
UNKNOWN_FILL = PatternFill("solid", fgColor="FFF2CC")
HEADER_FONT = Font(color="FFFFFF", bold=True)
THIN_BORDER = Border(bottom=Side(style="thin", color="AAB7BF"))
CORE_NAMESPACES = {
    "cp": "http://schemas.openxmlformats.org/package/2006/metadata/core-properties",
    "dc": "http://purl.org/dc/elements/1.1/",
    "dcterms": "http://purl.org/dc/terms/",
    "dcmitype": "http://purl.org/dc/dcmitype/",
    "xsi": "http://www.w3.org/2001/XMLSchema-instance",
}
for prefix, uri in CORE_NAMESPACES.items():
    ElementTree.register_namespace(prefix, uri)


def _normalize_archive(path: Path) -> None:
    normalized = path.with_name(f".{path.name}.tmp")
    with ZipFile(path) as source, ZipFile(
        normalized, "w", compression=ZIP_DEFLATED, compresslevel=9
    ) as target:
        for info in source.infolist():
            info.date_time = (1980, 1, 1, 0, 0, 0)
            info.create_system = 0
            data = source.read(info.filename)
            if info.filename == "docProps/core.xml":
                root = ElementTree.fromstring(data)
                modified = root.find(f"{{{CORE_NAMESPACES['dcterms']}}}modified")
                if modified is not None:
                    modified.text = "2026-07-12T00:00:00Z"
                data = ElementTree.tostring(root, encoding="utf-8")
            target.writestr(info, data)
    normalized.replace(path)


def _add_enumerations(workbook: Workbook) -> None:
    sheet = workbook.create_sheet("枚举值")
    for column, (range_name, (header, values)) in enumerate(ENUMS.items(), start=1):
        sheet.cell(1, column, header)
        for row, value in enumerate(values, start=2):
            sheet.cell(row, column, value)
        reference = f"{quote_sheetname(sheet.title)}!${get_column_letter(column)}$2:${get_column_letter(column)}${len(values) + 1}"
        workbook.defined_names.add(DefinedName(range_name, attr_text=reference))


def _style_sheet(sheet) -> None:
    sheet.freeze_panes = "A2"
    sheet.sheet_view.showGridLines = False
    sheet.sheet_view.zoomScale = 90
    sheet.auto_filter.ref = f"A1:{get_column_letter(sheet.max_column)}{max(1, sheet.max_row)}"
    sheet.row_dimensions[1].height = 28
    for cell in sheet[1]:
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = THIN_BORDER
    for column in range(1, sheet.max_column + 1):
        values = [str(sheet.cell(row, column).value or "") for row in range(1, min(sheet.max_row, 30) + 1)]
        width = min(max(max(map(len, values), default=8) + 2, 12), 42)
        sheet.column_dimensions[get_column_letter(column)].width = width
    for row in sheet.iter_rows(min_row=2):
        for cell in row:
            cell.alignment = Alignment(vertical="top", wrap_text=True)
            if cell.data_type == "f":
                cell.fill = FORMULA_FILL


def _add_validations(workbook: Workbook) -> None:
    for sheet_name, columns in VALIDATIONS.items():
        sheet = workbook[sheet_name]
        for column, range_name in columns.items():
            validation = DataValidation(type="list", formula1=f"={range_name}", allow_blank=True)
            validation.error = "请选择下拉列表中的值。"
            validation.errorTitle = "无效枚举值"
            validation.prompt = "请选择受控枚举值；未知不得填写为假。"
            validation.promptTitle = "受控字段"
            validation.showErrorMessage = True
            validation.showInputMessage = True
            sheet.add_data_validation(validation)
            validation.add(f"{column}2:{column}{MAX_DATA_ROW}")


def build_workbook(output_path: str | Path = DEFAULT_OUTPUT) -> Path:
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    workbook = Workbook()
    workbook.remove(workbook.active)
    workbook.properties.creator = "Va1ha11a_demo"
    workbook.properties.title = "Bayesian parameter collection template"
    workbook.properties.created = datetime(2026, 7, 12, tzinfo=timezone.utc)
    workbook.properties.modified = datetime(2026, 7, 12, tzinfo=timezone.utc)

    for sheet_name, rows in SHEET_ROWS.items():
        sheet = workbook.create_sheet(sheet_name)
        for row in rows:
            sheet.append(row)
        for cell, formula in FORMULAS.get(sheet_name, {}).items():
            sheet[cell] = formula

    _add_enumerations(workbook)
    _add_validations(workbook)
    for sheet in workbook.worksheets:
        _style_sheet(sheet)

    workbook["原子事实核验"].conditional_formatting.add(
        f"G2:G{MAX_DATA_ROW}", FormulaRule(formula=['G2="未知"'], fill=UNKNOWN_FILL)
    )
    workbook.save(output)
    _normalize_archive(output)
    return output


if __name__ == "__main__":
    print(build_workbook())
