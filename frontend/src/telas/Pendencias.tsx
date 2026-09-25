import { useState } from "react";

import { Erro } from "../App";
import { api, type Pendencia } from "../api";
import { CartaoEvidencia } from "./Laudo";
import { useCarregar } from "./Vistoria";

const TITULO_POR_TIPO: Record<string, string> = {
  scope_conflict: "Conflito de escopo",
  falta: "Item que a foto mostra e o laudo não tem",
  repetido: "Item repetido em várias linhas",
  certeza: "Item com certeza baixa",
};

/**
 * Tela de auditoria (regra 20).
 *
 * O que ela mostra em cada pendência: cômodo, categoria, item, motivo,
 * confiança, a foto relacionada e a evidência — com a miniatura ao lado, para
 * a decisão ser tomada olhando a imagem, não o texto.
 *
 * O que ela NÃO faz: decidir. Nenhuma pendência se resolve sozinha, e não há
 * botão de "aceitar todas".
 */
export function PainelPendencias({
  vistoriaId,
  aoDecidir,
}: {
  vistoriaId: string;
  aoDecidir: () => Promise<void>;
}) {
  const { dados, erro, recarregar } = useCarregar<Pendencia[]>(
    () => api.pendencias(vistoriaId),
    [vistoriaId],
  );

  if (erro) return <Erro erro={erro} />;
  if (!dados) return <div className="vazio">Carregando…</div>;

  if (dados.length === 0) {
    return (
      <div className="vazio">
        <p>Nenhuma pendência em aberto.</p>
        <p className="fraco">O laudo está liberado para conferência final.</p>
      </div>
    );
  }

  return (
    <>
      <p className="fraco" style={{ marginTop: 0 }}>
        {dados.length} pendência(s). Conflitos de escopo vêm primeiro: são os itens
        que o sistema recusou atribuir ao cômodo e que só você pode decidir.
      </p>
      {dados.map((pendencia) => (
        <CartaoPendencia
          key={pendencia.id}
          pendencia={pendencia}
          aoResolver={async () => {
            await recarregar();
            await aoDecidir();
          }}
        />
      ))}
    </>
  );
}

function CartaoPendencia({
  pendencia,
  aoResolver,
}: {
  pendencia: Pendencia;
  aoResolver: () => Promise<void>;
}) {
  const proposta = pendencia.tipo === "falta" || pendencia.tipo === "scope_conflict";
  const [correcao, setCorrecao] = useState(pendencia.texto_proposto || pendencia.item_texto);
  const [regra, setRegra] = useState("");
  const [razao, setRazao] = useState("");
  const [erro, setErro] = useState<unknown>(null);
  const [enviando, setEnviando] = useState(false);
  const [aviso, setAviso] = useState<string | null>(null);

  async function decidir(decisao: "OK" | "CORRIGIR" | "REMOVER") {
    setErro(null);
    setEnviando(true);
    try {
      const resposta = await api.decidir(pendencia.id, {
        decisao,
        correcao: decisao === "CORRIGIR" ? correcao : "",
        regra: regra.trim(),
        tipo_correcao: pendencia.tipo === "scope_conflict" ? "AMBIENTE_ADJACENTE" : "",
        razao: razao.trim(),
      });
      if (resposta.regra_adotada) {
        setAviso(`Regra adotada para as próximas vistorias: ${resposta.regra_adotada}`);
      }
      await aoResolver();
    } catch (falha) {
      setErro(falha);
    } finally {
      setEnviando(false);
    }
  }

  return (
    <div className="cartao">
      <div className="entre">
        <div>
          <span className="linha">
            <span className="etiqueta neutra">{pendencia.comodo}</span>
            <span className="etiqueta neutra">{pendencia.rotulo}</span>
            <span
              className={pendencia.tipo === "scope_conflict" ? "etiqueta perigo" : "etiqueta alerta"}
            >
              {TITULO_POR_TIPO[pendencia.tipo] ?? pendencia.tipo}
            </span>
            {pendencia.tipo === "certeza" && (
              <span className="etiqueta alerta">certeza {pendencia.certeza}%</span>
            )}
          </span>
        </div>
      </div>

      <p style={{ margin: "10px 0 0" }}>{pendencia.motivo}</p>

      {pendencia.item_texto && (
        <p style={{ margin: "10px 0 0", fontWeight: 600 }}>{pendencia.item_texto}</p>
      )}
      {proposta && pendencia.texto_proposto && !pendencia.item_texto && (
        <p style={{ margin: "10px 0 0" }}>
          <span className="fraco">Proposta (ainda não está no laudo): </span>
          {pendencia.texto_proposto}
        </p>
      )}

      {pendencia.evidencias.length > 0 && (
        <div className="lista-cartoes" style={{ marginTop: 12 }}>
          {pendencia.evidencias.map((evidencia) => (
            <CartaoEvidencia key={evidencia.id} evidencia={evidencia} />
          ))}
        </div>
      )}

      <Erro erro={erro} />
      {aviso && <div className="aviso" style={{ marginTop: 10 }}>{aviso}</div>}

      <label htmlFor={`correcao-${pendencia.id}`}>
        {proposta ? "Texto para o laudo (se aceitar)" : "Texto corrigido"}
      </label>
      <textarea
        id={`correcao-${pendencia.id}`}
        value={correcao}
        onChange={(e) => setCorrecao(e.target.value)}
        placeholder="*Uma porta em madeira na cor branca, ..."
      />

      <label htmlFor={`razao-${pendencia.id}`}>Por quê? (opcional, fica registrado)</label>
      <input
        id={`razao-${pendencia.id}`}
        value={razao}
        onChange={(e) => setRazao(e.target.value)}
        placeholder="ex.: conferi na foto, a parede é do corredor"
      />

      <label htmlFor={`regra-${pendencia.id}`}>
        Virar regra geral? (opcional — vale para TODA vistoria futura)
      </label>
      <input
        id={`regra-${pendencia.id}`}
        value={regra}
        onChange={(e) => setRegra(e.target.value)}
        placeholder="Só preencha se o erro vale para qualquer imóvel"
      />
      <p className="fraco" style={{ marginTop: 4 }}>
        Fato deste imóvel não é regra geral — resolva só com Corrigir ou Remover.
      </p>

      <div className="linha" style={{ marginTop: 12 }}>
        <button className="principal" onClick={() => decidir("OK")} disabled={enviando}>
          {proposta ? "Aceitar no laudo" : "Está certo"}
        </button>
        <button onClick={() => decidir("CORRIGIR")} disabled={enviando || !correcao.trim()}>
          {proposta ? "Aceitar com meu texto" : "Corrigir"}
        </button>
        <button className="perigo" onClick={() => decidir("REMOVER")} disabled={enviando}>
          {proposta ? "Descartar" : "Remover do laudo"}
        </button>
      </div>
    </div>
  );
}
