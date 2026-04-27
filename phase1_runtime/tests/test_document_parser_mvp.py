from __future__ import annotations

from base64 import b64encode
from io import BytesIO
import unittest
from unittest.mock import patch
import zipfile

import openpyxl

from phase1_runtime.parsing import parse_uploaded_materials


def _make_pdf_bytes(text: str) -> bytes:
    objects = []
    objects.append('1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n')
    objects.append('2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n')
    objects.append('3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 144] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>\nendobj\n')
    stream = f'BT\n/F1 12 Tf\n72 72 Td\n({text}) Tj\nET\n'
    objects.append(f'4 0 obj\n<< /Length {len(stream.encode())} >>\nstream\n{stream}endstream\nendobj\n')
    objects.append('5 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n')
    content = '%PDF-1.4\n'
    offsets = []
    for obj in objects:
        offsets.append(len(content.encode('latin-1')))
        content += obj
    xref_offset = len(content.encode('latin-1'))
    content += f'xref\n0 {len(objects)+1}\n'
    content += '0000000000 65535 f \n'
    for offset in offsets:
        content += f'{offset:010d} 00000 n \n'
    content += f'trailer\n<< /Size {len(objects)+1} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF\n'
    return content.encode('latin-1')


def _make_docx_bytes(paragraphs: list[str]) -> bytes:
    document_xml = [
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>',
    ]
    for paragraph in paragraphs:
        document_xml.append(f'<w:p><w:r><w:t>{paragraph}</w:t></w:r></w:p>')
    document_xml.append('</w:body></w:document>')
    buf = BytesIO()
    with zipfile.ZipFile(buf, 'w') as archive:
        archive.writestr('[Content_Types].xml', '<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"></Types>')
        archive.writestr('word/document.xml', ''.join(document_xml))
    return buf.getvalue()


def _make_xlsx_bytes(rows: list[list[object]]) -> bytes:
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.title = 'Sheet1'
    for row in rows:
        sheet.append(row)
    buf = BytesIO()
    workbook.save(buf)
    return buf.getvalue()


class BrokenPdf(BytesIO):
    pass




class DocumentParserMvpTests(unittest.TestCase):
    def test_parse_pdf_material(self) -> None:
        with patch(
            "phase1_runtime.parsing.document_parser_mvp.understand_pdf_bytes",
            return_value={
                "title": "Sample PDF",
                "document_family": "financial_report",
                "blocks": [
                    {
                        "block_id": "block_001",
                        "block_type": "paragraph",
                        "section": "body",
                        "page": 1,
                        "text": "Threshold 0.80",
                    }
                ],
                "semantic_signals": [],
            },
        ):
            payload = parse_uploaded_materials(
                [
                    {
                        'name': 'sample.pdf',
                        'content_base64': b64encode(_make_pdf_bytes('Threshold 0.80')).decode('ascii'),
                    }
                ],
                scenario_id='fund_nav_warning',
            )
        material = payload['parsed_materials'][0]
        self.assertEqual(material['parse_status'], 'parsed_pdf_kimi')
        self.assertIn('Threshold 0.80', material['content'])
        self.assertEqual(material['line_items'][0]['locator']['page'], 1)

    def test_parse_pdf_material_passes_query_text_to_understanding_layer(self) -> None:
        with patch(
            "phase1_runtime.parsing.document_parser_mvp.understand_pdf_bytes",
            return_value={
                "title": "Sample PDF",
                "document_family": "financial_report",
                "blocks": [
                    {
                        "block_id": "block_001",
                        "block_type": "paragraph",
                        "section": "body",
                        "page": 1,
                        "text": "Threshold 0.80",
                    }
                ],
                "semantic_signals": [],
            },
        ) as mock_understand:
            parse_uploaded_materials(
                [
                    {
                        'name': 'sample.pdf',
                        'content_base64': b64encode(_make_pdf_bytes('Threshold 0.80')).decode('ascii'),
                    }
                ],
                scenario_id='fund_nav_warning',
                question_text='净值跌破阈值后是否需要风险提示？',
            )
        self.assertEqual(mock_understand.call_args.kwargs["query_text"], '净值跌破阈值后是否需要风险提示？')

    def test_parse_pdf_uses_structured_blocks_from_understanding_layer(self) -> None:
        with patch(
            "phase1_runtime.parsing.document_parser_mvp.understand_pdf_bytes",
            return_value={
                "title": "Research PDF",
                "document_family": "equity_research_report",
                "blocks": [
                    {
                        "block_id": "block_001",
                        "block_type": "title",
                        "section": "cover",
                        "page": 1,
                        "text": "工商银行（601398）：息差压力缓解，资产质量稳中有进",
                    },
                    {
                        "block_id": "block_002",
                        "block_type": "paragraph",
                        "section": "rating",
                        "page": 1,
                        "text": "维持增持评级。",
                    },
                ],
                "semantic_signals": [{"signal_type": "rating_candidate", "value": "增持", "page": 1}],
            },
        ):
            payload = parse_uploaded_materials(
                [
                    {
                        'name': 'sample.pdf',
                        'content_base64': b64encode(_make_pdf_bytes('Threshold 0.80')).decode('ascii'),
                    }
                ],
                scenario_id='equity_research',
            )
        material = payload['parsed_materials'][0]
        self.assertEqual(material['parse_status'], 'parsed_pdf_kimi')
        self.assertEqual(material['doc_type'], 'report')
        self.assertEqual(material['title'], 'Research PDF')
        self.assertEqual(material['line_items'][0]['locator']['section'], 'cover')
        self.assertEqual(material['line_items'][1]['locator']['block_type'], 'paragraph')

    def test_parse_pdf_returns_parse_error_when_understanding_layer_fails(self) -> None:
        with patch(
            "phase1_runtime.parsing.document_parser_mvp.understand_pdf_bytes",
            side_effect=RuntimeError("kimi plugin failed"),
        ):
            payload = parse_uploaded_materials(
                [
                    {
                        'name': 'sample.pdf',
                        'content_base64': b64encode(_make_pdf_bytes('Threshold 0.80')).decode('ascii'),
                    }
                ],
                scenario_id='fund_nav_warning',
            )
        material = payload['parsed_materials'][0]
        self.assertEqual(material['parse_status'], 'parse_error')
        self.assertIn('kimi plugin failed', material['warnings'][0])

    def test_parse_docx_material(self) -> None:
        payload = parse_uploaded_materials(
            [
                {
                    'name': 'sample.docx',
                    'content_base64': b64encode(_make_docx_bytes(['合同约定在到期前5日内应通知借款人办理展期手续。'])).decode('ascii'),
                }
            ],
            scenario_id='credit_notice',
        )
        material = payload['parsed_materials'][0]
        self.assertEqual(material['parse_status'], 'parsed_docx_text')
        self.assertIn('合同约定在到期前5日内应通知借款人办理展期手续。', material['content'])
        self.assertEqual(material['line_items'][0]['locator']['paragraph'], 1)

    def test_parse_xlsx_material(self) -> None:
        payload = parse_uploaded_materials(
            [
                {
                    'name': 'schedule.xlsx',
                    'content_base64': b64encode(_make_xlsx_bytes([['当前贷款距离到期日还有20天', 20]])).decode('ascii'),
                }
            ],
            scenario_id='credit_notice',
        )
        material = payload['parsed_materials'][0]
        self.assertEqual(material['parse_status'], 'parsed_xlsx_text')
        self.assertIn('当前贷款距离到期日还有20天', material['content'])
        self.assertEqual(material['line_items'][0]['locator']['sheet'], 'Sheet1')
