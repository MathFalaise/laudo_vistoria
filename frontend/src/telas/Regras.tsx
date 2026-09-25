import { useState } from "react";

import { Erro } from "../App";
import { api, type Regra } from "../api";
import { useCarregar } from "./Vistoria";

/**
 * Regras de redação adotadas.
 *
 * Elas entram no prompt de TODA vistoria futura. Por isso a tela é explícita
 * sobre o que não pode entrar aqui: fato de um imóvel específico. "A cozinha
 * não tem porta" viraria "nenhuma cozinha tem porta".
 */
export function TelaRegras() {
  const { dados, erro, recarregar } = useCarregar<Regra[]>(() => api.regras(), []);
  const [texto, setTexto] = useState("");
  const [falha, setFalha] = useState<unknown>(null);

  async function criar() {
    if (!texto.trim()) return;
    setFalha(null);
    try {
      await api.criarRegra(texto.trim());
      setTexto("");
      await recarregar();
    } catch (erroNovo) {
      setFalha(erroNovo);
    }
  }

  const ativas = dados?.filter((regra) => regra.ativa) ?? [];
  const inativas = dados?.filter((regra) => !regra.ativa) ?? [];

  return (
    <main className="conteudo">
      <h1 style={{ fontSize: 20, marginTop: 0 }}>Regras de redação</h1>
      <p className="fraco">
        Valem para toda vistoria daqui em diante. Nunca escreva aqui endereço, nome
        de cliente ou detalhe de um imóvel.
      </p>

      <Erro erro={erro} />
      <Erro erro={falha} />

      <div className="cartao">
        <label htmlFor="nova">Nova regra</label>
        <textarea
          id="nova"
          value={texto}
          onChange={(e) => setTexto(e.target.value)}
          placeholder="Ex.: O vaso sanitário entra sempre na Mobília do banheiro."
        />
        <div style={{ marginTop: 10 }}>
          <button className="principal" onClick={criar} disabled={texto.trim().length < 5}>
            Adotar regra
          </button>
        </div>
      </div>

      <h2 style={{ fontSize: 16 }}>Em vigor ({ativas.length})</h2>
      {ativas.map((regra) => (
        <div key={regra.id} className="cartao">
          <p style={{ margin: 0 }}>{regra.texto}</p>
          <div className="entre" style={{ marginTop: 8 }}>
            <span className="fraco">
              {regra.origem}
              {regra.adotada_em && ` · ${new Date(regra.adotada_em).toLocaleDateString("pt-BR")}`}
            </span>
            <button
              className="pequeno perigo"
              onClick={async () => {
                if (!confirm("Desativar esta regra para as próximas vistorias?")) return;
                await api.desativarRegra(regra.id);
                await recarregar();
              }}
            >
              Desativar
            </button>
          </div>
        </div>
      ))}

      {inativas.length > 0 && (
        <>
          <h2 style={{ fontSize: 16 }}>Desativadas ({inativas.length})</h2>
          {inativas.map((regra) => (
            <div key={regra.id} className="cartao" style={{ opacity: 0.6 }}>
              <p style={{ margin: 0 }}>{regra.texto}</p>
            </div>
          ))}
        </>
      )}
    </main>
  );
}
