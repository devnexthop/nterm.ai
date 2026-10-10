/** Save a text file through the OS picker when we have it, else a real <a download>.

Chromium cancels blob downloads if the object URL is revoked in the same turn as
click(), which is why Settings → Download tree looked like a no-op.
*/
export function datedName(prefix: string, ext: string) {
  const d = new Date();
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${prefix}-${y}${m}${day}.${ext}`;
}

export async function saveTextFile(
  filename: string,
  text: string,
  mime = "application/json",
): Promise<"saved" | "cancelled"> {
  const blob = new Blob([text], { type: `${mime};charset=utf-8` });
  const picker = (window as unknown as {
    showSaveFilePicker?: (opts: {
      suggestedName: string;
      types: { description: string; accept: Record<string, string[]> }[];
    }) => Promise<{
      createWritable: () => Promise<{ write: (b: Blob) => Promise<void>; close: () => Promise<void> }>;
    }>;
  }).showSaveFilePicker;

  if (typeof picker === "function") {
    try {
      const handle = await picker({
        suggestedName: filename,
        types: [{ description: "NTerm sessions", accept: { [mime]: [`.${filename.split(".").pop() || "json"}`] } }],
      });
      const writable = await handle.createWritable();
      await writable.write(blob);
      await writable.close();
      return "saved";
    } catch (err) {
      if (err instanceof DOMException && err.name === "AbortError") return "cancelled";
    }
  }

  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.rel = "noopener";
  a.style.display = "none";
  document.body.appendChild(a);
  a.click();
  window.setTimeout(() => {
    a.remove();
    URL.revokeObjectURL(url);
  }, 4000);
  return "saved";
}
