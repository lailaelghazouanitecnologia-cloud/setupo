declare module "@novnc/novnc/lib/rfb" {
  export default class RFB extends EventTarget {
    constructor(
      target: Element,
      urlOrChannel: string | unknown,
      options?: {
        credentials?: { password?: string };
        shared?: boolean;
      },
    );

    scaleViewport: boolean;
    clipViewport: boolean;
    focusOnClick: boolean;
    qualityLevel: number;
    compressionLevel: number;

    connect(): void;
    disconnect(): void;
    focus(): void;
    sendCredentials(credentials: { password?: string }): void;
    clipboardPasteFrom(text: string): void;
    sendCtrlAltDel(): void;
  }
}
