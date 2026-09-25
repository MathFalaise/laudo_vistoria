import { useState } from "react";

import { Erro } from "../App";
import { api, type Evidencia, type ItemLaudo, type Laudo } from "../api";
import { useCarregar } from "./Vistoria";

export function PainelLaudo({ vistoriaId }: { vistoriaId: string }) {
  const { dados, erro, recarregar } = useCarregar<Laudo>(
    () => api.laudo(vistoriaId),
    [vistoriaId],
  );
  const [comoTexto, setComoTexto] = useState(false);

  if (erro) return <Erro erro={erro} />;
  if (!dados) return <div className="vazio">Carregando…</div>;

  const vazio = dados.comodos.every((comodo) => comodo.categorias.length === 0);
  if (vazio) {
    return (
      <div className="vazio">
        <p>O laudo ainda não foi escrito.</p>
        <p className="fraco">Envie as fotos e use o botão Processar.</p>
      </div>
    );
  }

  return (
    <>
      <div className="entre" style={{ marginBottom: 12 }}>
        <h2 style={{ fontSize: 18, margin: 0 }}>Laudo</h2>
        <button className="pequeno" onClick={() => setComoTexto((v) => !v)}>
          {comoTexto ? "Ver por cômodo" : "Ver como texto"}
        </button>
      </div>

      {comoTexto ? (
        <pre className="laudo">{dados.texto}</pre>
      ) : (
        dados.comodos
          .filter((comodo) => comodo.categorias.length > 0)
          .map((comodo) => (
            <div key={comodo.id} className="cartao">
              <div className="entre">
                <h3 style={{ margin: 0 }}>{comodo.nome}</h3>
                {comodo.cobertura_incompleta && (
                  <span className="etiqueta alerta">cobertura incompleta</span>
                )}
              </div>
              {comodo.categorias.map((categoria) => (
                <div key={categoria.categoria} style={{ marginTop: 12 }}>
                  <h4 style={{ margin: "0 0 4px", fontSize: 14 }}>{categoria.rotulo}</h4>
                  {categoria.itens.map((item) => (
                    <LinhaItem
                      key={item.id}
                      item={item}
                      comodoId={comodo.id}
                      aoSalvar={recarregar}
                    />
                  ))}
                </div>
              ))}
            </div>
          ))
      )}
    </>
  );
}

function LinhaItem({
  item,
  comodoId,
  aoSalvar,
}: {
  item: ItemLaudo;
  comodoId: string;
  aoSalvar: () => Promise<void>;
}) {
  const [editando, setEditando] = useState(false);
  const [texto, setTexto] = useState(item.texto);
  const [evidencias, setEvidencias] = useState<Evidencia[] | null>(null);
  const [erro, setErro] = useState<unknown>(null);

  async function verEvidencias() {
    if (evidencias) {
      setEvidencias(null);
      return;
    }
    try {
      const todas = await api.evidencias(comodoId);
      setEvidencias(todas.filter((e) => item.evidencias.includes(e.id)));
    } catch (falha) {
      setErro(falha);
    }
  }

  async function salvar() {
    setErro(null);
    try {
      await api.editarItem(item.id, texto);
      setEditando(false);
      await aoSalvar();
    } catch (falha) {
      setErro(falha);
    }
  }

  return (
    <div style={{ borderTop: "1px solid var(--borda)", padding: "8px 0" }}>
      <Erro erro={erro} />
      {editando ? (
        <>
          <textarea value={texto} onChange={(e) => setTexto(e.target.value)} />
          <div className="linha" style={{ marginTop: 8 }}>
            <button className="principal pequeno" onClick={salvar}>Salvar</button>
            <button className="pequeno" onClick={() => { setTexto(item.texto); setEditando(false); }}>
              Cancelar
            </button>
          </div>
        </>
      ) : (
        <>
          <p style={{ margin: 0 }}>{item.texto}</p>
          <div className="linha" style={{ marginTop: 6 }}>
            {item.certeza < 85 && (
              <span className="etiqueta alerta" title={item.motivo}>
                certeza {item.certeza}%
              </span>
            )}
            <button className="pequeno" onClick={() => setEditando(true)}>Editar</button>
            {item.evidencias.length > 0 && (
              <button className="pequeno" onClick={verEvidencias}>
                {evidencias ? "Ocultar" : `${item.evidencias.length} evidência(s)`}
              </button>
            )}
          </div>
        </>
      )}

      {evidencias && (
        <div className="lista-cartoes" style={{ marginTop: 10 }}>
          {evidencias.map((evidencia) => (
            <CartaoEvidencia key={evidencia.id} evidencia={evidencia} />
          ))}
        </div>
      )}
    </div>
  );
}

/**
 * Evidência com a foto de onde ela saiu e, quando existe, o retângulo da
 * região. É o que responde "de onde saiu esta frase do laudo?".
 */
export function CartaoEvidencia({ evidencia }: { evidencia: Evidencia }) {
  return (
    <div className="auditoria">
      <a className="moldura" href={api.urlFoto(evidencia.foto_id)} target="_blank" rel="noreferrer">
        <img src={api.urlMiniatura(evidencia.foto_id, 480)} alt={evidencia.observacao} loading="lazy" />
        {evidencia.regiao && (
          <span
            className="regiao"
            style={{
              left: `${evidencia.regiao.x * 100}%`,
              top: `${evidencia.regiao.y * 100}%`,
              width: `${evidencia.regiao.largura * 100}%`,
              height: `${evidencia.regiao.altura * 100}%`,
            }}
          />
        )}
      </a>
      <div>
        <p style={{ margin: "0 0 6px" }}>{evidencia.observacao}</p>
        <div className="linha">
          <span className="etiqueta neutra">{evidencia.rotulo}</span>
          <span className="etiqueta info" title="O quanto a imagem deixa claro o que é">
            percepção {evidencia.confianca_percepcao}%
          </span>
          <span
            className={evidencia.confianca_escopo >= 70 ? "etiqueta ok" : "etiqueta perigo"}
            title="O quanto isto pertence a ESTE cômodo"
          >
            escopo {evidencia.confianca_escopo}%
          </span>
          {evidencia.reflexo && <span className="etiqueta alerta">reflexo</span>}
          {evidencia.ambiente_adjacente && (
            <span className="etiqueta perigo">ambiente vizinho</span>
          )}
        </div>
        {evidencia.status !== "aceita" && (
          <p className="fraco" style={{ marginTop: 6, marginBottom: 0 }}>
            Não entrou no laudo: {evidencia.detalhe_descarte || evidencia.motivo_descarte}
          </p>
        )}
      </div>
    </div>
  );
}
