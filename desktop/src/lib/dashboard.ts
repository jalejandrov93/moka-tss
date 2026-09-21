export type CardId =
  | "servicios"
  | "mascota"
  | "mascota-detalle"
  | "sistema"
  | "transmision"
  | "wsl"
  | "reglas";

const DEFAULT_CARDS: CardId[] = [
  "servicios",
  "mascota",
  "mascota-detalle",
  "sistema",
  "transmision",
  "wsl",
  "reglas",
];

const STORAGE_KEY = "moka.cards";

export function loadVisible(): CardId[] {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (!stored) return DEFAULT_CARDS;
    const parsed = JSON.parse(stored);
    if (!Array.isArray(parsed)) return DEFAULT_CARDS;
    // Validate all items are valid CardId
    const valid = parsed.filter((id): id is CardId =>
      DEFAULT_CARDS.includes(id as CardId)
    );
    return valid.length > 0 ? valid : DEFAULT_CARDS;
  } catch {
    return DEFAULT_CARDS;
  }
}

export function saveVisible(cards: CardId[]): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(cards));
  } catch {
    // Ignore localStorage errors (private browsing, quota exceeded, etc.)
  }
}

export function getAllCardIds(): CardId[] {
  return [...DEFAULT_CARDS];
}

export function getCardLabel(id: CardId): string {
  const labels: Record<CardId, string> = {
    servicios: "Servicios",
    mascota: "Mascota",
    "mascota-detalle": "Mascota Detalle",
    sistema: "Sistema",
    transmision: "Transmisión",
    wsl: "WSL",
    reglas: "Reglas",
  };
  return labels[id];
}