"use strict";

const $ = (id) => document.getElementById(id);

// Sempre textContent (nunca innerHTML com dados da API): evita XSS.
function el(tag, attrs = {}, ...filhos) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v);
  for (const f of filhos) e.append(f instanceof Node ? f : document.createTextNode(String(f)));
  return e;
}

function mensagem(texto, tipo) {
  const box = $("resultado");
  box.replaceChildren(el("div", { class: `msg ${tipo}` }, texto));
}

$("btn-local").addEventListener("click", () => {
  if (!navigator.geolocation) {
    $("local-status").textContent = "Seu navegador não oferece localização.";
    return;
  }
  $("local-status").textContent = "Buscando localização...";
  navigator.geolocation.getCurrentPosition(
    (pos) => {
      $("lat").value = pos.coords.latitude.toFixed(6);
      $("lon").value = pos.coords.longitude.toFixed(6);
      $("local-status").textContent = `Localização definida (precisão de ~${Math.round(pos.coords.accuracy)} m).`;
    },
    () => { $("local-status").textContent = "Não foi possível obter a localização. Verifique a permissão."; },
    { enableHighAccuracy: true, timeout: 15000 }
  );
});

$("form-relato").addEventListener("submit", async (ev) => {
  ev.preventDefault();
  const foto = $("foto").files[0];
  if (!foto) return mensagem("Escolha ou tire uma foto.", "erro");
  if (!$("lat").value) return mensagem("Toque em \"Usar minha localização\" antes de enviar.", "erro");

  const dados = new FormData();
  dados.append("foto", foto);
  dados.append("lat", $("lat").value);
  dados.append("lon", $("lon").value);

  $("btn-enviar").disabled = true;
  try {
    const r = await fetch("/api/v1/relatos", { method: "POST", body: dados });
    const j = await r.json();
    if (!r.ok) return mensagem(j.erro || "Não foi possível enviar.", "erro");
    const ia = j.analise_ia;
    let txt = `${j.mensagem} Análise da IA: iluminação ${ia.classificacao} (confiança ${Math.round(ia.confianca * 100)}%).`;
    if (j.chamado) txt += ` Chamado #${j.chamado.id}, prioridade ${j.chamado.prioridade}.`;
    mensagem(txt, "ok");
    $("form-relato").reset();
    carregar();
  } catch {
    mensagem("Sem conexão. Tente de novo quando o sinal melhorar.", "erro");
  } finally {
    $("btn-enviar").disabled = false;
  }
});

async function carregar() {
  try {
    const [rc, rs] = await Promise.all([
      fetch("/api/v1/chamados?limite=20"),
      fetch("/api/v1/estatisticas"),
    ]);
    const { chamados } = await rc.json();
    const st = await rs.json();

    $("stats").replaceChildren(
      el("div", {}, `Ativos: ${st.chamados_ativos}`),
      el("div", {}, `Relatos: ${st.total_relatos}`),
      el("div", {}, `Duplicados agrupados: ${st.relatos_agrupados_por_deduplicacao}`),
      el("div", {}, `Validados por sensor: ${st.chamados_com_validacao_fisica}`)
    );

    const lista = $("lista-chamados");
    if (!chamados.length) {
      lista.replaceChildren(el("li", {}, "Nenhum chamado ainda."));
      return;
    }
    lista.replaceChildren(...chamados.map((c) => {
      const parada = c.parada_proxima ? ` · ${c.parada_proxima.distancia_m} m de ${c.parada_proxima.nome}` : "";
      const det = el("details", {}, el("summary", {}, "Por que esta prioridade?"));
      fetch(`/api/v1/chamados/${c.id}`).then((r) => r.json()).then((d) => {
        const ul = el("ul");
        (d.explicacao_prioridade || []).forEach((m) => ul.append(el("li", {}, m)));
        det.append(ul);
      });
      return el("li", {},
        el("span", { class: `badge ${c.classificacao}` }, c.classificacao), " ",
        `Chamado #${c.id}, prioridade ${c.prioridade}, ${c.status.replace("_", " ")}, ${c.qtd_relatos} relato(s)${parada}`,
        det);
    }));
  } catch {
    $("lista-chamados").replaceChildren(el("li", {}, "Não foi possível carregar a fila."));
  }
}

carregar();
