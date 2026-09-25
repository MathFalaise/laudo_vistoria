import { useEffect, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";

import { Erro } from "../App";
import { api, type Vistoria } from "../api";

export function ListaVistorias() {
  const [vistorias, setVistorias] = useState<Vistoria[]>([]);
  const [erro, setErro] = useState<unknown>(null);
  const [titulo, setTitulo] = useState("");
  const [notas, setNotas] = useState("");
  const [criando, setCriando] = useState(false);
  const [importando, setImportando] = useState(false);

  async function recarregar() {
    try {
      setVistorias(await api.vistorias());
    } catch (falha) {
      setErro(falha);
    }
  }

  useEffect(() => {
    void recarregar();
  }, []);

  async function criar(evento: FormEvent) {
    evento.preventDefault();
    setErro(null);
    try {
      await api.criarVistoria({ titulo: titulo.trim(), notas: notas.trim() });
      setTitulo("");
      setNotas("");
      setCriando(false);
      await recarregar();
    } catch (falha) {
      setErro(falha);
    }
  }

  async function importar(arquivo: File) {
    setErro(null);
    setImportando(true);
    const dados = new FormData();
    dados.append("titulo", arquivo.name.replace(/\.zip$/i, ""));
    dados.append("arquivo", arquivo);
    try {
      const resposta = await fetch("/api/importar", {
        method: "POST",
        body: dados,
        credentials: "include",
      });
      if (!resposta.ok) throw new Error((await resposta.json()).detail ?? "Falha ao importar.");
      await recarregar();
    } catch (falha) {
      setErro(falha);
    } finally {
      setImportando(false);
    }
  }

  return (
    <main className="conteudo">
      <div className="entre" style={{ marginBottom: 12 }}>
        <h1 style={{ fontSize: 20, margin: 0 }}>Vistorias</h1>
        <div className="linha">
          <label className="botao pequeno" style={{ margin: 0 }}>
            {importando ? "Importando…" : "Importar antiga"}
            <input
              type="file"
              accept=".zip"
              hidden
              onChange={(e) => e.target.files?.[0] && importar(e.target.files[0])}
            />
          </label>
          <button className="principal pequeno" onClick={() => setCriando((v) => !v)}>
            Nova vistoria
          </button>
        </div>
      </div>

      <Erro erro={erro} />

      {criando && (
        <form className="cartao" onSubmit={criar}>
          <label htmlFor="titulo">Imóvel</label>
          <input
            id="titulo"
            value={titulo}
            onChange={(e) => setTitulo(e.target.value)}
            placeholder="R. Exemplo, 100 — AP 31"
            required
          />
          <label htmlFor="notas">
            Informações confirmadas do imóvel
          </label>
          <textarea
            id="notas"
            value={notas}
            onChange={(e) => setNotas(e.target.value)}
            placeholder={
              "Cor exata das tintas, material do piso, testes feitos…\n" +
              "Ex.: Paredes na cor Branco Gelo. Teto em gesso Branco Neve.\n" +
              "Todos os testes elétricos e hidráulicos foram feitos."
            }
          />
          <p className="fraco" style={{ marginTop: 6 }}>
            Estas notas descrevem o padrão da casa. Onde a foto mostrar acabamento
            diferente, vale a foto.
          </p>
          <div className="linha" style={{ marginTop: 12 }}>
            <button className="principal" type="submit">Criar</button>
            <button type="button" onClick={() => setCriando(false)}>Cancelar</button>
          </div>
        </form>
      )}

      {vistorias.length === 0 && !criando ? (
        <div className="vazio">
          <p>Nenhuma vistoria ainda.</p>
          <p className="fraco">Crie uma nova ou importe uma pasta de vistoria antiga em ZIP.</p>
        </div>
      ) : (
        <div className="lista-cartoes duas">
          {vistorias.map((vistoria) => (
            <Link key={vistoria.id} to={`/vistorias/${vistoria.id}`} className="cartao" style={{ display: "block", color: "inherit", textDecoration: "none" }}>
              <h2>{vistoria.titulo}</h2>
              <p className="fraco" style={{ margin: "2px 0 10px" }}>
                {new Date(vistoria.criado_em).toLocaleDateString("pt-BR")}
              </p>
              <div className="linha">
                <span className="etiqueta neutra">{vistoria.comodos} cômodo(s)</span>
                <span className="etiqueta neutra">{vistoria.fotos} foto(s)</span>
                {vistoria.pendencias.abertas > 0 ? (
                  <span
                    className={
                      vistoria.pendencias.por_tipo.scope_conflict
                        ? "etiqueta perigo"
                        : "etiqueta alerta"
                    }
                  >
                    {vistoria.pendencias.abertas} pendência(s)
                  </span>
                ) : (
                  <span className="etiqueta ok">sem pendências</span>
                )}
              </div>
            </Link>
          ))}
        </div>
      )}
    </main>
  );
}
