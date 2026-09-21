import React, { useEffect } from "react";
import { getOrderedVisibleCards } from "@/lib/dashboard";
import { cardRenderers, renderTemaCard, currentTheme } from "@/main";

export function Dashboard(): React.ReactElement {
  const cardIdsToRender = getOrderedVisibleCards(currentTheme);

  const visibleCardElements = cardIdsToRender
    .map((id) => cardRenderers[id])
    .filter(Boolean)
    .map((fn) => fn());

  const hasBackground = Boolean(
    currentTheme.backgroundImage && currentTheme.backgroundImage.trim() !== ""
  );
  const containerStyle: React.CSSProperties = hasBackground
    ? {
        backgroundImage: `linear-gradient(rgba(2, 6, 23, 0.85), rgba(2, 6, 23, 0.85)), url("${currentTheme.backgroundImage}")`,
        backgroundSize: "cover",
        backgroundPosition: "center",
        backgroundAttachment: "fixed",
        backgroundRepeat: "no-repeat",
      }
    : {};

  useEffect(() => {
    if (typeof document !== "undefined" && document.body) {
      if (hasBackground) {
        document.body.style.backgroundImage = `linear-gradient(rgba(2, 6, 23, 0.85), rgba(2, 6, 23, 0.85)), url("${currentTheme.backgroundImage}")`;
        document.body.style.backgroundSize = "cover";
        document.body.style.backgroundPosition = "center";
        document.body.style.backgroundAttachment = "fixed";
        document.body.style.backgroundRepeat = "no-repeat";
      } else {
        document.body.style.backgroundImage = "";
        document.body.style.backgroundSize = "";
        document.body.style.backgroundPosition = "";
        document.body.style.backgroundAttachment = "";
        document.body.style.backgroundRepeat = "";
      }
    }
  }, [hasBackground, currentTheme.backgroundImage]);

  return (
    <div
      className="min-h-full w-full bg-slate-950 text-slate-50 p-6 flex flex-col items-center gap-6"
      style={containerStyle}
    >
      {renderTemaCard()}
      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-6 w-full max-w-[96rem]">
        {visibleCardElements}
      </div>
    </div>
  );
}

export default Dashboard;
