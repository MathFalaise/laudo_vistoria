import { useEffect, useState } from "react";

import { Erro } from "../App";
import { api, type Comodo, type Foto } from "../api";
import { EstadoComodo } from "./Vistoria";

/**
 * Tela de fotos — a que mais importa no celular (regra 36): o vistoriador
 * está de pé no imóvel, cria o cômodo e manda as fotos dali mesmo.
 *
 * O <input capture> abre a câmera direto no telefone; o arrastar-e-soltar
 * serve ao desktop. Os dois caem no mesmo envio.
 */
export function PainelFotos({
  vistoriaId,
  comodos,
  aoMudar,
}: {
  vistoriaId: string;
  comodos: Comodo[];
  aoMudar: () => Promise<void>;
}) {
  const [nome, setNome] = useState("");
  const [erro, setErro] = useState<unknown>(null);
  const [aberto, setAberto] = useState<string | null>(null);
  const [enviandoZip, setEnviandoZip] = useState(false);

  useEffect(() => {
    if (aberto === null && comodos.length > 0) setAberto(comodos[0].id);
  }, [comodos, aberto]);

  async function criarComodo() {
    const limpo = nome.trim();
    if (!limpo) return;
    setErro(null);
    try {
      const comodo = await api.criarComodo(vistoriaId, limpo);
      setNome("");
      await aoMudar();
      setAberto(comodo.id);
    } catch (falha) {
      setErro(falha);
    }
  }

  async function enviarZip(arquivo: File) {
    setErro(null);
    setEnviandoZip(true);
    try {
      const resposta = await api.enviarZip(vistoriaId, arquivo);
      if (resposta.recusadas.length) {
        setErro(new Error(`${resposta.recusadas.length} arquivo(s) recusado(s): ` +
          resposta.recusadas.slice(0, 3).map((r) => `${r.nome} — ${r.motivo}`).join("; ")));
      }
      await aoMudar();
    } catch (falha) {
      setErro(falha);
    } finally {
      setEnviandoZip(false);
    }
  }

  return (
    <>
      <Erro erro={erro} />

      <div className="cartao">
        <h3>Cômodos</h3>
        <div className="linha">
          <input
            value={nome}
            onChange={(e) => setNome(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && criarComodo()}
            placeholder="Cozinha, Quarto 01, BWC Social…"
            style={{ flex: 1, minWidth: 180 }}
          />
          <button className="principal" onClick={criarComodo} disabled={!nome.trim()}>
            Criar
          </button>
        </div>
        <div className="linha" style={{ marginTop: 10 }}>
          <label className="botao pequeno" style={{ margin: 0 }}>
            {enviandoZip ? "Enviando…" : "Enviar ZIP com pastas por cômodo"}
            <input
              type="file"
              accept=".zip"
              hidden
              onChange={(e) => e.target.files?.[0] && enviarZip(e.target.files[0])}
            />
          </label>
        </div>
      </div>

      {comodos.length === 0 ? (
        <div className="vazio">
          <p>Nenhum cômodo ainda.</p>
          <p className="fraco">Crie o primeiro acima, ou mande o ZIP da vistoria.</p>
        </div>
      ) : (
        comodos.map((comodo) => (
          <CartaoComodo
            key={comodo.id}
            comodo={comodo}
            aberto={aberto === comodo.id}
            aoAbrir={() => setAberto(aberto === comodo.id ? null : comodo.id)}
            aoMudar={aoMudar}
          />
        ))
      )}
    </>
  );
}

function CartaoComodo({
  comodo,
  aberto,
  aoAbrir,
  aoMudar,
}: {
  comodo: Comodo;
  aberto: boolean;
  aoAbrir: () => void;
  aoMudar: () => Promise<void>;
}) {
  const [fotos, setFotos] = useState<Foto[]>([]);
  const [erro, setErro] = useState<unknown>(null);
  const [arrastando, setArrastando] = useState(false);
  const [enviando, setEnviando] = useState(false);
  const [recusadas, setRecusadas] = useState<{ nome: string; motivo: string }[]>([]);

  async function carregarFotos() {
    try {
      setFotos(await api.fotos(comodo.id));
    } catch (falha) {
      setErro(falha);
    }
  }

  useEffect(() => {
    if (aberto) void carregarFotos();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [aberto, comodo.id]);

  async function enviar(arquivos: File[]) {
    if (!arquivos.length) return;
    setErro(null);
    setRecusadas([]);
    setEnviando(true);
    try {
      const resposta = await api.enviarFotos(comodo.id, arquivos);
      setRecusadas(resposta.recusadas);
      await carregarFotos();
      await aoMudar();
    } catch (falha) {
      setErro(falha);
    } finally {
      setEnviando(false);
    }
  }

  async function apagar(foto: Foto) {
    if (!confirm(`Remover "${foto.nome_original}" desta vistoria?`)) return;
    try {
      await api.apagarFoto(foto.id);
      await carregarFotos();
      await aoMudar();
    } catch (falha) {
      setErro(falha);
    }
  }

  return (
    <div className="cartao">
      <button
        onClick={aoAbrir}
        style={{
          all: "unset",
          cursor: "pointer",
          display: "flex",
          width: "100%",
          gap: 8,
          alignItems: "center",
          justifyContent: "space-between",
          minHeight: 44,
        }}
      >
        <span style={{ fontWeight: 600 }}>
          {aberto ? "▾" : "▸"} {comodo.nome}
        </span>
        <span className="linha">
          <span className="etiqueta neutra">{comodo.fotos} foto(s)</span>
          {comodo.pendencias_abertas > 0 && (
            <span className="etiqueta alerta">{comodo.pendencias_abertas} pend.</span>
          )}
          <EstadoComodo comodo={comodo} />
        </span>
      </button>

      {comodo.cobertura_incompleta && (
        <div className="aviso" style={{ marginTop: 10 }}>
          As fotos não cobrem o cômodo inteiro. O sistema não concluiu ausência de
          item nenhum — confira no imóvel antes de entregar.
        </div>
      )}
      {comodo.erro && <div className="erro" style={{ marginTop: 10 }}>{comodo.erro}</div>}

      {aberto && (
        <div style={{ marginTop: 12 }}>
          <Erro erro={erro} />
          {recusadas.length > 0 && (
            <div className="aviso" style={{ marginBottom: 10 }}>
              {recusadas.length} arquivo(s) recusado(s):
              <ul style={{ margin: "6px 0 0 18px", padding: 0 }}>
                {recusadas.map((r) => (
                  <li key={r.nome}>
                    <strong>{r.nome}</strong> — {r.motivo}
                  </li>
                ))}
              </ul>
            </div>
          )}

          <div
            className={`solta${arrastando ? " ativa" : ""}`}
            onDragOver={(e) => {
              e.preventDefault();
              setArrastando(true);
            }}
            onDragLeave={() => setArrastando(false)}
            onDrop={(e) => {
              e.preventDefault();
              setArrastando(false);
              void enviar(Array.from(e.dataTransfer.files));
            }}
          >
            {enviando ? (
              "Enviando…"
            ) : (
              <>
                <p style={{ margin: "0 0 10px" }}>Arraste as fotos aqui, ou:</p>
                <div className="linha" style={{ justifyContent: "center" }}>
                  <label className="botao" style={{ margin: 0 }}>
                    Escolher arquivos
                    <input
                      type="file"
                      accept="image/jpeg,image/png,image/heic,image/heif,.heic,.heif"
                      multiple
                      hidden
                      onChange={(e) => {
                        void enviar(Array.from(e.target.files ?? []));
                        e.target.value = "";
                      }}
                    />
                  </label>
                  <label className="botao" style={{ margin: 0 }}>
                    Câmera
                    <input
                      type="file"
                      accept="image/*"
                      capture="environment"
                      multiple
                      hidden
                      onChange={(e) => {
                        void enviar(Array.from(e.target.files ?? []));
                        e.target.value = "";
                      }}
                    />
                  </label>
                </div>
                <p className="fraco" style={{ margin: "10px 0 0" }}>JPG, PNG ou HEIC</p>
              </>
            )}
          </div>

          {fotos.length > 0 && (
            <div className="grade-fotos" style={{ marginTop: 12 }}>
              {fotos.map((foto) => (
                <figure key={foto.id} className="foto" style={{ margin: 0 }}>
                  <a href={api.urlFoto(foto.id)} target="_blank" rel="noreferrer">
                    <img src={api.urlMiniatura(foto.id, 320)} alt={foto.nome_original} loading="lazy" />
                  </a>
                  <button className="remover" onClick={() => apagar(foto)} title="Remover">
                    ×
                  </button>
                  {foto.escopo === "out_of_scope" && (
                    <span className="selo fora" title={foto.motivo_escopo}>fora do cômodo</span>
                  )}
                  {foto.escopo === "partial" && (
                    <span className="selo parcial" title={foto.motivo_escopo}>parcial</span>
                  )}
                </figure>
              ))}
            </div>
          )}

          <div className="linha" style={{ marginTop: 12, justifyContent: "flex-end" }}>
            <button
              className="perigo pequeno"
              onClick={async () => {
                if (!confirm(`Apagar o cômodo "${comodo.nome}" e todas as fotos dele?`)) return;
                await api.apagarComodo(comodo.id);
                await aoMudar();
              }}
            >
              Apagar cômodo
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
