// Faux DOM des tests sous node (story 4.7) : arbre avec parents, attributs, classes, événements,
// `dialog` (`show`, `showModal`, `close` dont l'événement est différé comme dans un navigateur),
// `matchMedia` pilotable, `document.contains`. Importé par les scripts de tests/test_web_*.py.

export const journal = [];

export class Evenement {
  constructor(type, init = {}) {
    Object.assign(this, init);
    this.type = type;
    this.defaultPrevented = false;
  }

  preventDefault() {
    this.defaultPrevented = true;
  }
}

export class N {
  constructor(t, ns) {
    this.t = t;
    this.ns = ns || null;
    this.a = {};
    this.k = [];
    this.parent = null;
    this.x = "";
    this.ev = {};
    this.vus = [];
    this.open = false;
    this.modal = false;
    this.hidden = false;
  }

  get className() { return this.a.class || ""; }
  set className(v) { this.a.class = String(v); }
  get id() { return this.a.id || ""; }
  set id(v) { this.a.id = String(v); }

  get classList() {
    const noeud = this;
    const lire = () => noeud.className.split(" ").filter(Boolean);
    return {
      add: (c) => { if (!lire().includes(c)) { noeud.className = [...lire(), c].join(" "); } },
      remove: (c) => { noeud.className = lire().filter((x) => x !== c).join(" "); },
      contains: (c) => lire().includes(c),
    };
  }

  setAttribute(n, v) { this.a[n] = String(v); }
  getAttribute(n) { return Object.hasOwn(this.a, n) ? this.a[n] : null; }
  removeAttribute(n) { delete this.a[n]; }
  addEventListener(t, f) { (this.ev[t] = this.ev[t] || []).push(f); }
  dispatchEvent(e) {
    for (const f of this.ev[e.type] || []) { f(e); }
    return !e.defaultPrevented;
  }
  click() { this.dispatchEvent(new Evenement("click")); }

  append(...e) {
    for (const n of e) {
      if (n.parent) { n.parent.removeChild(n); }
      n.parent = this;
      this.k.push(n);
    }
  }
  appendChild(n) { this.append(n); return n; }
  removeChild(n) { this.k = this.k.filter((c) => c !== n); n.parent = null; return n; }
  remove() { if (this.parent) { this.parent.removeChild(this); } }
  insertBefore(n, ref) {
    if (n.parent) { n.parent.removeChild(n); }
    n.parent = this;
    const i = ref === null ? -1 : this.k.indexOf(ref);
    if (i < 0) { this.k.push(n); } else { this.k.splice(i, 0, n); }
    return n;
  }
  get childNodes() { return this.k; }
  get firstChild() { return this.k[0] || null; }
  contains(n) {
    for (let m = n; m; m = m.parent) { if (m === this) { return true; } }
    return false;
  }
  get textContent() { return this.x + this.k.map((c) => c.textContent).join(""); }
  set textContent(v) {
    for (const c of this.k) { c.parent = null; }
    this.k = [];
    this.x = String(v);
  }
  correspond(s) {
    if (s.startsWith(".")) { return this.className.split(" ").includes(s.slice(1)); }
    if (s.startsWith("#")) { return this.id === s.slice(1); }
    return this.t === s;
  }
  querySelectorAll(s) {
    const r = [];
    const visiter = (n) => { for (const c of n.k) { if (c.correspond(s)) { r.push(c); } visiter(c); } };
    visiter(this);
    return r;
  }
  querySelector(s) { return this.querySelectorAll(s)[0] || null; }
  focus() { document.activeElement = this; }
  scrollIntoView(o) { this.vus.push(o || null); }

  show() {
    if (this.open) { throw new Error("InvalidStateError : déjà ouvert"); }
    this.open = true; this.modal = false; journal.push("show");
  }
  showModal() {
    if (this.open) { throw new Error("InvalidStateError : déjà ouvert"); }
    this.open = true; this.modal = true; journal.push("showModal");
  }
  // Comme un navigateur : `open` tombe tout de suite, l'événement `close` part au tour suivant.
  close() {
    if (!this.open) { return; }
    this.open = false; this.modal = false; journal.push("close");
    setTimeout(() => this.dispatchEvent(new Evenement("close")), 0);
  }
}

export const body = new N("body");
export const annonces = [];

const regions = {
  annonce: { set textContent(v) { if (v) { annonces.push(String(v)); } } },
  alerte: { set textContent(v) { if (v) { journal.push(`alerte:${v}`); } } },
};

globalThis.document = {
  body,
  activeElement: null,
  ev: {},
  createElement: (t) => new N(t),
  createElementNS: (ns, t) => new N(t, ns),
  getElementById: (id) => regions[id] || body.querySelector(`#${id}`),
  querySelector: (s) => body.querySelector(s),
  contains: (n) => body.contains(n),
  addEventListener(t, f) { (this.ev[t] = this.ev[t] || []).push(f); },
  dispatchEvent(e) {
    for (const f of this.ev[e.type] || []) { f(e); }
    return !e.defaultPrevented;
  },
};

// `matchMedia` : une requête par appel, pilotée par `largeur(vrai|faux)`.
export const requetes = [];
let large = true;
export function largeur(valeur) {
  large = valeur;
  for (const r of requetes) {
    r.matches = valeur;
    for (const f of r.ev.change || []) { f({ matches: valeur }); }
  }
}

globalThis.window = globalThis.window || {};
Object.assign(globalThis.window, {
  setTimeout: (f, ms) => setTimeout(f, 0),
  clearTimeout: (id) => clearTimeout(id),
  setInterval: (f) => { globalThis.window.periodique = f; return 1; },
  clearInterval: () => {},
  addEventListener: () => {},
  matchMedia: (q) => {
    const r = { media: q, matches: large, ev: {},
      addEventListener(t, f) { (this.ev[t] = this.ev[t] || []).push(f); } };
    requetes.push(r);
    return r;
  },
  location: { hash: "", pathname: "/", search: "" },
  history: { replaceState: () => {} },
});

// Laisse passer les tâches différées (événement `close`, réponses de fetch, régions d'annonce).
export async function tour(n = 5) {
  for (let i = 0; i < n; i += 1) {
    await new Promise((r) => setTimeout(r, 0));
  }
}

export const tous = (n) => [n, ...n.k.flatMap(tous)];
export const parClasse = (n, c) => tous(n).filter((x) => x.className.split(" ").includes(c));
export const parBalise = (n, t) => tous(n).filter((x) => x.t === t);
export const texte = (n) => n.textContent;
export const textes = (n) => tous(n).map((x) => x.x).filter(Boolean);
export const touche = (key, init = {}) => document.dispatchEvent(new Evenement("keydown", { key, ...init }));
