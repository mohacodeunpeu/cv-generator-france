// ─── Photo professionnelle : import, recadrage, taille, modes. Jamais retouchée (ni filtre, ni lissage) ──
// Stockée dans la base privée (pai/photo), jamais dans Git ni dans une URL. Le PDF reçoit un carré et un disque recadrés.
const PHOTO_MODES = [['AUTO', 'Auto'], ['HEADER', 'En-tête'], ['SIDEBAR', 'Colonne'], ['OFF', 'Sans photo']];
const PHOTO_SIZES = [[0.85, 'S'], [1, 'M'], [1.15, 'L']];
const loadImg = (src) => new Promise((res, rej) => { const i = new Image(); i.onload = () => res(i); i.onerror = () => rej(new Error('Image illisible')); i.src = src; });

const Photo = {
  MAX: 820, LOW: 300,
  async fromFile(file) {
    if (!/^image\/(png|jpe?g|webp)$/.test(file.type || '')) throw new Error('Format non pris en charge : PNG, JPEG ou WebP.');
    if (file.size > 15e6) throw new Error('Image trop lourde (15 Mo maximum).');
    const url = URL.createObjectURL(file);
    try {
      const img = await loadImg(url);
      // Stockage privé : 256 Kio par document → image ramenée sous ~180 Ko (taille puis qualité), sans autre traitement.
      let max = Photo.MAX; let q = 0.92; let data = ''; let w = 0; let h = 0;
      for (let i = 0; i < 8; i++) {
        const k = Math.min(1, max / Math.max(img.naturalWidth, img.naturalHeight));
        w = Math.max(1, Math.round(img.naturalWidth * k)); h = Math.max(1, Math.round(img.naturalHeight * k));
        const c = document.createElement('canvas'); c.width = w; c.height = h;
        const g = c.getContext('2d'); g.imageSmoothingQuality = 'high'; g.drawImage(img, 0, 0, w, h);
        data = c.toDataURL('image/jpeg', q);
        if (data.length <= 180000) break;
        if (q > 0.8) q -= 0.06; else max = Math.round(max * 0.8);
      }
      const portrait = h >= w;
      return { v: 1, data, w, h, orig_w: img.naturalWidth, orig_h: img.naturalHeight,
        crop: { x: 0.5, y: portrait ? 0.42 : 0.5, zoom: portrait ? 1.12 : 1 }, scale: 1, name: String(file.name || 'photo').slice(0, 80), updated_at: nowIso() };
    } finally { URL.revokeObjectURL(url); }
  },
  rect(p) {
    const z = Math.max(1, Math.min(3, (p.crop && p.crop.zoom) || 1)); const side = Math.min(p.w, p.h) / z;
    const cx = Math.max(side / 2, Math.min(p.w - side / 2, ((p.crop && p.crop.x) ?? 0.5) * p.w));
    const cy = Math.max(side / 2, Math.min(p.h - side / 2, ((p.crop && p.crop.y) ?? 0.5) * p.h));
    return { sx: cx - side / 2, sy: cy - side / 2, side, z };
  },
  // Résolution utile : pixels d'origine réellement couverts par le recadrage.
  px(p) { const r = Photo.rect(p); return Math.round(r.side * ((p.orig_w || p.w) / p.w)); },
  lowRes(p) { return !!p && Photo.px(p) < Photo.LOW; },
  async refresh() {
    const p = S.photo;
    if (!p || !p.data) { S.photoAssets = null; PDF.invalidate(); render(); return; }
    try {
      const img = await loadImg(p.data); const r = Photo.rect(p);
      const out = Math.max(96, Math.min(640, Math.round(r.side * 2)));
      const sq = document.createElement('canvas'); sq.width = sq.height = out;
      const g = sq.getContext('2d'); g.imageSmoothingQuality = 'high'; g.drawImage(img, r.sx, r.sy, r.side, r.side, 0, 0, out, out);
      const ci = document.createElement('canvas'); ci.width = ci.height = out;
      const h = ci.getContext('2d'); h.beginPath(); h.arc(out / 2, out / 2, out / 2, 0, Math.PI * 2); h.closePath(); h.clip(); h.drawImage(sq, 0, 0);
      S.photoAssets = { id: E.hash([p.updated_at, p.crop, p.w, p.h, p.data.length]), square: sq.toDataURL('image/jpeg', 0.93), circle: ci.toDataURL('image/png'), px: Photo.px(p), lowRes: Photo.lowRes(p) };
    } catch (e) { console.warn('photo', e); S.photoAssets = null; }
    PDF.invalidate(); render();
  },
  // Aperçu dans le cadre de réglage (même recadrage que le PDF).
  frameStyle(p, size) {
    const r = Photo.rect(p); const k = size / r.side;
    return `width:${Math.round(p.w * k)}px;height:${Math.round(p.h * k)}px;transform:translate(${Math.round(-r.sx * k)}px,${Math.round(-r.sy * k)}px)`;
  },
  mode() { return (S.prefs && S.prefs.photo_mode) || 'AUTO'; },
};

// Carte « Ma photo » : utilisée dans Profil, dans l'onboarding et depuis CV Studio.
function photoManager(opts = {}) {
  const p = S.photo; const A = S.photoAssets; const mode = Photo.mode(); const size = (p && p.scale) || 1;
  const frame = p ? `<div class="photo-frame${opts.square ? ' square' : ''}" id="photo-frame" data-drag="photo" aria-label="Glisse pour recadrer"><img src="${p.data}" alt="Ta photo professionnelle" draggable="false" style="${Photo.frameStyle(p, 150)}"></div>`
    : `<label class="photo-frame empty" for="f-photo" data-drop-photo="1"><svg class="ico" aria-hidden="true"><use href="#i-camera"/></svg><span>Ajouter</span></label>`;
  return `<div class="card stack" id="photo-card">
    <div class="card-head"><h3 class="h3">Ma photo</h3>${p ? (A && A.lowRes ? chip(`Basse résolution · ${A.px} px`, 'warn') : A ? chip(`${A.px} px · nette`, 'good') : '') : chip('Aucune photo', '')}</div>
    <div class="photo-box">${frame}
      <div class="stack">
        ${p ? `<div class="field"><label for="photo-zoom">Cadrage (zoom)</label><input id="photo-zoom" class="range" type="range" min="1" max="2.6" step="0.02" value="${esc(p.crop.zoom)}" data-change="photo-zoom"></div>
          <div class="field"><span class="label">Taille sur le CV</span><div class="seg" role="group" aria-label="Taille de la photo">${PHOTO_SIZES.map(([v, l]) => `<button data-act="photo-size" data-arg="${v}" aria-pressed="${Math.abs(size - v) < 0.01}">${l}</button>`).join('')}</div></div>` : ''}
        <div class="field"><span class="label">Position par défaut</span><div class="seg" role="group" aria-label="Mode photo">${PHOTO_MODES.map(([k, l]) => `<button data-act="photo-mode" data-arg="${k}" aria-pressed="${mode === k}">${l}</button>`).join('')}</div>
          <span class="hint">${({ AUTO: 'PAI décide selon le pays, le secteur et le design (ex. sans photo si l\'ATS est prioritaire).', HEADER: 'Photo dans l\'en-tête quand le pays l\'accepte.', SIDEBAR: 'Colonne latérale (design Digital Creative) ; en-tête pour les autres designs.', OFF: 'Jamais de photo sur tes CV.' })[mode]}</span></div>
        <div class="row"><label class="btn sm" for="f-photo">${icon('i-upload')} ${p ? 'Remplacer' : 'Importer une photo'}</label><input id="f-photo" type="file" accept="image/png,image/jpeg,image/webp" class="sr" data-change="photo-file">
          ${p ? `<button class="btn sm ghost danger" data-act="photo-delete">${icon('i-x')} Retirer</button>` : ''}</div>
      </div></div>
    ${A && A.lowRes ? `<div class="notice warn">${icon('i-alert')}<span>Photo en basse résolution (${A.px} px utiles) : elle reste utilisable, mais peut paraître floue à l'impression. Si tu as une version plus grande (≥ 400 px), remplace-la.</span></div>` : ''}
    <p class="hint" style="margin:0">PAI ne retouche jamais ton visage : recadrage et taille uniquement. La photo reste privée (base de ton serveur PAI ou stockage privé claude.ai), jamais dans Git ni dans une URL.</p>
  </div>`;
}
