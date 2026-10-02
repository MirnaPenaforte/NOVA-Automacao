import csv
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import api


class ApiJsonTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.imports_dir = Path(self.temp_dir.name)
        self.imports_dir_original = api.IMPORTS_DIR
        api.IMPORTS_DIR = self.imports_dir

    def tearDown(self):
        api.IMPORTS_DIR = self.imports_dir_original
        self.temp_dir.cleanup()

    def _criar_csv(self, prefixo, linhas, colunas=None):
        caminho = self.imports_dir / f"{prefixo}_12-09-2026.csv"
        with caminho.open("w", encoding="latin-1", newline="") as arquivo:
            csv.writer(arquivo, delimiter=";").writerows(linhas)
        if colunas is not None:
            caminho.with_suffix(".columns.json").write_text(
                json.dumps(colunas), encoding="utf-8"
            )
        return caminho

    def test_json_organizado_nas_quatro_categorias(self):
        arquivos = {
            "METAS": (
                self._criar_csv(
                    "METAS", [["10", "100", "2026-09-12"]],
                    ["Vendedor", "Meta", "Data"]
                ),
                "METAS",
            ),
            "VENDAS": (
                self._criar_csv(
                    "VENDA", [["5102", "12/09/2026"]],
                    ["CFOP", "Saida_Data_Venda"]
                ),
                "VENDA",
            ),
            "VENDEDORES": (
                self._criar_csv(
                    "VENDEDORES", [["10", "João"]], ["Codigo", "Nome"]
                ),
                "VENDEDORES",
            ),
            "ESTOQUE": (
                self._criar_csv(
                    "ESTOQUE", [["789", "7"]], ["EAN", "Quantidade"]
                ),
                "ESTOQUE",
            ),
        }
        tabelas = {
            categoria: (arquivo, api._obter_colunas(arquivo, prefixo))
            for categoria, (arquivo, prefixo) in arquivos.items()
        }

        with patch("api._ano_vigente", return_value=2026):
            resultado = json.loads("".join(api._gerar_json(tabelas)))

        self.assertEqual(
            list(resultado), ["METAS", "VENDAS", "VENDEDORES", "ESTOQUE"]
        )
        self.assertEqual(resultado["METAS"], [
            {"Vendedor": "10", "Meta": "100", "Data": "12/09/2026"}
        ])
        self.assertEqual(resultado["VENDAS"][0]["CFOP"], "5102")
        self.assertEqual(resultado["VENDEDORES"][0]["Nome"], "João")
        self.assertEqual(resultado["ESTOQUE"][0]["Quantidade"], "7")

    def test_csv_antigo_sem_esquema_recebe_nomes_genericos(self):
        arquivo = self._criar_csv("VENDEDORES", [["10", "100", ""]])
        colunas = api._obter_colunas(arquivo, "VENDEDORES")
        resultado = json.loads(
            "".join(api._gerar_json({"VENDEDORES": (arquivo, colunas)}))
        )

        self.assertEqual(colunas, ["coluna_1", "coluna_2", "coluna_3"])
        self.assertIsNone(resultado["VENDEDORES"][0]["coluna_3"])

    def test_datas_do_get_sao_formatadas_sem_alterar_outros_valores(self):
        arquivo = self._criar_csv(
            "ESTOQUE",
            [["2026-10-02", "2028/08/21", "", "7890123456789"],
             ["data-invalida", "02/10/2026", "2026-02-30", "000123"]],
            ["Data_Entrada", "Data_Vencimento", "Data_Validade", "Codigo_Barras"],
        )
        colunas = api._obter_colunas(arquivo, "ESTOQUE")
        resultado = json.loads(
            "".join(api._gerar_json({"ESTOQUE": (arquivo, colunas)}))
        )["ESTOQUE"]

        self.assertEqual(resultado[0], {
            "Data_Entrada": "02/10/2026",
            "Data_Vencimento": "21/08/2028",
            "Data_Validade": None,
            "Codigo_Barras": "7890123456789",
        })
        self.assertEqual(resultado[1], {
            "Data_Entrada": "data-invalida",
            "Data_Vencimento": "02/10/2026",
            "Data_Validade": "2026-02-30",
            "Codigo_Barras": "000123",
        })

    def test_valores_decimais_do_get_tem_duas_casas(self):
        arquivo = self._criar_csv(
            "VENDA",
            [["59.5000", "12.345", "21,8", "6230.0", "2.0000", "2026-10-02"],
             ["", "invalido", "0.001", "000123.0", "3", "2026/10/02"]],
            ["Valor", "Saida_Valor_Unitario_Item", "Preco_Custo",
             "Cliente_Codigo", "Saida_Quantidade", "Saida_Data_Venda"],
        )
        colunas = api._obter_colunas(arquivo, "VENDA")
        with patch("api._ano_vigente", return_value=2026):
            resultado = json.loads(
                "".join(api._gerar_json({"VENDAS": (arquivo, colunas)}))
            )["VENDAS"]

        self.assertEqual(resultado[0], {
            "Valor": "59.50",
            "Saida_Valor_Unitario_Item": "12.35",
            "Preco_Custo": "21.80",
            "Cliente_Codigo": "6230",
            "Saida_Quantidade": 2,
            "Saida_Data_Venda": "02/10/2026",
        })
        self.assertEqual(resultado[1], {
            "Valor": None,
            "Saida_Valor_Unitario_Item": "invalido",
            "Preco_Custo": "0.00",
            "Cliente_Codigo": "000123",
            "Saida_Quantidade": 3,
            "Saida_Data_Venda": "02/10/2026",
        })

    def test_ano_vigente_muda_a_cada_geracao_do_json(self):
        arquivos = {
            "METAS": self._criar_csv(
                "METAS",
                [["2026-12-31"], ["2027-01-01"], ["data-invalida"]],
                ["Data"],
            ),
            "VENDAS": self._criar_csv(
                "VENDA", [["31/12/2026"], ["2027/01/01"]],
                ["Saida_Data_Venda"],
            ),
            "VENDEDORES": self._criar_csv(
                "VENDEDORES", [["10"]], ["Vendedor_Codigo"]
            ),
            "ESTOQUE": self._criar_csv(
                "ESTOQUE", [["2025-10-16", "2028-08-21"]],
                ["Data_Entrada", "Data_Vencimento"],
            ),
        }
        tabelas = {
            categoria: (arquivo, api._obter_colunas(arquivo, categoria))
            for categoria, arquivo in arquivos.items()
        }

        with patch("api._ano_vigente", return_value=2026):
            resultado_2026 = json.loads("".join(api._gerar_json(tabelas)))
        with patch("api._ano_vigente", return_value=2027):
            resultado_2027 = json.loads("".join(api._gerar_json(tabelas)))

        self.assertEqual(resultado_2026["METAS"], [{"Data": "31/12/2026"}])
        self.assertEqual(resultado_2027["METAS"], [{"Data": "01/01/2027"}])
        self.assertEqual(
            resultado_2026["VENDAS"], [{"Saida_Data_Venda": "31/12/2026"}]
        )
        self.assertEqual(
            resultado_2027["VENDAS"], [{"Saida_Data_Venda": "01/01/2027"}]
        )
        for resultado in (resultado_2026, resultado_2027):
            self.assertEqual(resultado["VENDEDORES"], [{"Vendedor_Codigo": "10"}])
            self.assertEqual(resultado["ESTOQUE"], [{
                "Data_Entrada": "16/10/2025",
                "Data_Vencimento": "21/08/2028",
            }])

    def test_arquivo_atual_filtrado_nao_e_publicado(self):
        self._criar_csv("VENDA_ATUAL", [["dado"]])
        self.assertIsNone(api._arquivo_atual("VENDA"))


if __name__ == "__main__":
    unittest.main()
