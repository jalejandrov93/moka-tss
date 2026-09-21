import type { ThemeConfig, ThemeCard } from "../types";

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

export function isCardId(id: string): id is CardId {
  return (DEFAULT_CARDS as string[]).includes(id);
}

export function getDefaultTheme(): ThemeConfig {
  return {
    id: "default",
    name: "Por defecto",
    cards: DEFAULT_CARDS.map((id, index) => ({
      id,
      visible: true,
      order: index,
    })),
    mascotVariant: "default",
  };
}

export interface ResolvedCard {
  id: CardId;
  visible: boolean;
  order: number;
}

export function resolveThemeCards(cards: ThemeCard[] | undefined | null): ResolvedCard[] {
  const allCardIds = getAllCardIds();
  const rawCards = Array.isArray(cards) ? cards : [];

  const seen = new Set<CardId>();
  const knownCards: ResolvedCard[] = [];

  for (const item of rawCards) {
    if (!item || typeof item.id !== "string") continue;
    if (!isCardId(item.id)) continue; // ids desconocidos se ignoran
    if (seen.has(item.id)) continue;
    seen.add(item.id);
    knownCards.push({
      id: item.id,
      visible: item.visible !== false,
      order: typeof item.order === "number" && !Number.isNaN(item.order) ? item.order : 0,
    });
  }

  // Sort known cards by order ascending
  knownCards.sort((a, b) => a.order - b.order);

  // Cards without entry maintain relative order at the end
  let maxOrder = knownCards.length > 0 ? Math.max(...knownCards.map((c) => c.order)) : -1;
  const unconfiguredCards: ResolvedCard[] = [];
  for (const id of allCardIds) {
    if (!seen.has(id)) {
      maxOrder += 1;
      unconfiguredCards.push({
        id,
        visible: true,
        order: maxOrder,
      });
    }
  }

  return [...knownCards, ...unconfiguredCards];
}

export function getOrderedVisibleCards(theme?: ThemeConfig | null): CardId[] {
  const resolved = resolveThemeCards(theme?.cards);
  return resolved.filter((c) => c.visible).map((c) => c.id);
}

export function updateThemeCardVisibility(
  theme: ThemeConfig,
  cardId: CardId,
  visible: boolean
): ThemeConfig {
  const cards = Array.isArray(theme.cards) ? theme.cards : [];
  const existing = cards.find((c) => c.id === cardId);

  let newCards: ThemeCard[];
  if (existing) {
    newCards = cards.map((c) =>
      c.id === cardId ? { ...c, visible } : c
    );
  } else {
    const resolved = resolveThemeCards(cards);
    const item = resolved.find((c) => c.id === cardId);
    const order = item ? item.order : cards.length;
    newCards = [...cards, { id: cardId, visible, order }];
  }

  return {
    ...theme,
    cards: newCards,
  };
}

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