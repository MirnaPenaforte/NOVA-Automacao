import csv
import json
import tempfile
import unittest
from pathlib import Path

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
                    "METAS", [["10", "100"]], ["Vendedor", "Meta"]
                ),
                "METAS",
            ),
            "VENDAS": (
                self._criar_csv(
                    "VENDA", [["5102", "12/09/2026"]], ["CFOP", "Data"]
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

        resultado = json.loads("".join(api._gerar_json(tabelas)))

        self.assertEqual(
            list(resultado), ["METAS", "VENDAS", "VENDEDORES", "ESTOQUE"]
        )
        self.assertEqual(resultado["METAS"], [{"Vendedor": "10", "Meta": "100"}])
        self.assertEqual(resultado["VENDAS"][0]["CFOP"], "5102")
        self.assertEqual(resultado["VENDEDORES"][0]["Nome"], "João")
        self.assertEqual(resultado["ESTOQUE"][0]["Quantidade"], "7")

    def test_csv_antigo_sem_esquema_recebe_nomes_genericos(self):
        arquivo = self._criar_csv("METAS", [["10", "100", ""]])
        colunas = api._obter_colunas(arquivo, "METAS")
        resultado = json.loads(
            "".join(api._gerar_json({"METAS": (arquivo, colunas)}))
        )

        self.assertEqual(colunas, ["coluna_1", "coluna_2", "coluna_3"])
        self.assertIsNone(resultado["METAS"][0]["coluna_3"])

    def test_arquivo_atual_filtrado_nao_e_publicado(self):
        self._criar_csv("VENDA_ATUAL", [["dado"]])
        self.assertIsNone(api._arquivo_atual("VENDA"))


if __name__ == "__main__":
    unittest.main()
