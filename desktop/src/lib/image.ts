/**
 * Image pipeline utilities for theme backgrounds.
 * No external dependencies, DOM/Canvas APIs only.
 */

/**
 * Opens a file picker for image files (PNG, JPEG, WebP).
 * Rejects files larger than 2MB with a clear error.
 */
export async function pickImageFile(): Promise<File | null> {
  return new Promise((resolve, reject) => {
    const input = document.createElement("input");
    input.type = "file";
    input.accept = "image/png,image/jpeg,image/webp";
    input.style.display = "none";

    input.onchange = () => {
      const file = input.files?.[0] ?? null;
      document.body.removeChild(input);

      if (!file) {
        resolve(null);
        return;
      }

      const maxSize = 2 * 1024 * 1024; // 2MB
      if (file.size > maxSize) {
        reject(new Error(`File size ${(file.size / 1024 / 1024).toFixed(2)}MB exceeds 2MB limit`));
        return;
      }

      resolve(file);
    };

    input.oncancel = () => {
      document.body.removeChild(input);
      resolve(null);
    };

    // Handle case where user closes picker without selecting (no onchange, no oncancel in some browsers)
    // We use a timeout fallback
    const timeoutId = setTimeout(() => {
      if (document.body.contains(input)) {
        document.body.removeChild(input);
        resolve(null);
      }
    }, 30000); // 30 second timeout

    const originalOnChange = input.onchange;
    input.onchange = (event) => {
      clearTimeout(timeoutId);
      if (originalOnChange) originalOnChange.call(input, event);
    };

    document.body.appendChild(input);
    input.click();
  });
}

/**
 * Converts a File to a WebP data URL suitable for theme backgrounds.
 * Resizes to max 1920x1080 maintaining aspect ratio.
 * Quality: 0.85 WebP.
 * Rejects if result exceeds 400KB.
 */
export async function fileToThemeBackground(file: File): Promise<string> {
  // Validate input
  if (!(file instanceof File)) {
    throw new Error("Expected a File object");
  }

  const dataUrl = await fileToDataUrl(file);
  const image = await dataUrlToImage(dataUrl);
  const resizedDataUrl = await resizeAndEncodeToWebp(image, 1920, 1080, 0.85);

  // Check final size (base64 encoded data URL size approx)
  const base64Data = resizedDataUrl.split(",")[1] ?? "";
  const sizeInBytes = Math.round((base64Data.length * 3) / 4); // base64 overhead ~33%
  const maxSize = 400 * 1024; // 400KB

  if (sizeInBytes > maxSize) {
    throw new Error(
      `Resulting image ${(sizeInBytes / 1024).toFixed(1)}KB exceeds 400KB limit`
    );
  }

  return resizedDataUrl;
}

/**
 * Converts a File to a data URL using FileReader.
 */
function fileToDataUrl(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result as string);
    reader.onerror = () => reject(new Error("Failed to read file"));
    reader.readAsDataURL(file);
  });
}

/**
 * Creates an HTMLImageElement from a data URL.
 */
function dataUrlToImage(dataUrl: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => resolve(img);
    img.onerror = () => reject(new Error("Failed to load image"));
    img.src = dataUrl;
  });
}

/**
 * Resizes an image to fit within maxWidth x maxHeight maintaining aspect ratio,
 * then encodes as WebP with the given quality.
 */
function resizeAndEncodeToWebp(
  image: HTMLImageElement,
  maxWidth: number,
  maxHeight: number,
  quality: number
): Promise<string> {
  return new Promise((resolve, reject) => {
    // Calculate new dimensions maintaining aspect ratio
    let { width, height } = image;
    const aspectRatio = width / height;

    if (width > maxWidth) {
      width = maxWidth;
      height = width / aspectRatio;
    }
    if (height > maxHeight) {
      height = maxHeight;
      width = height * aspectRatio;
    }

    // Create canvas and draw resized image
    const canvas = document.createElement("canvas");
    canvas.width = Math.round(width);
    canvas.height = Math.round(height);

    const ctx = canvas.getContext("2d");
    if (!ctx) {
      reject(new Error("Failed to get canvas 2D context"));
      return;
    }

    // Enable high-quality scaling
    ctx.imageSmoothingEnabled = true;
    ctx.imageSmoothingQuality = "high";

    ctx.drawImage(image, 0, 0, canvas.width, canvas.height);

    try {
      const dataUrl = canvas.toDataURL("image/webp", quality);
      resolve(dataUrl);
    } catch (error) {
      reject(new Error(`Failed to encode image as WebP: ${error}`));
    }
  });
}