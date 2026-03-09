// Adapted from noVNC keyboard handling to get a stable DOM event -> X11 keysym mapping.

const XK_BackSpace = 0xff08;
const XK_Tab = 0xff09;
const XK_Return = 0xff0d;
const XK_Escape = 0xff1b;
const XK_Delete = 0xffff;
const XK_Home = 0xff50;
const XK_Left = 0xff51;
const XK_Up = 0xff52;
const XK_Right = 0xff53;
const XK_Down = 0xff54;
const XK_Page_Up = 0xff55;
const XK_Page_Down = 0xff56;
const XK_End = 0xff57;
const XK_Insert = 0xff63;
const XK_Shift_L = 0xffe1;
const XK_Shift_R = 0xffe2;
const XK_Control_L = 0xffe3;
const XK_Control_R = 0xffe4;
const XK_Caps_Lock = 0xffe5;
const XK_Alt_L = 0xffe9;
const XK_Alt_R = 0xffea;
const XK_Super_L = 0xffeb;
const XK_Super_R = 0xffec;
const XK_Menu = 0xff67;
const XK_Num_Lock = 0xff7f;
const XK_space = 0x20;

const DOM_KEY_TABLE: Record<string, [number, number, number, number]> = {
  Alt: [XK_Alt_L, XK_Alt_L, XK_Alt_R, XK_Alt_L],
  Backspace: [XK_BackSpace, XK_BackSpace, XK_BackSpace, XK_BackSpace],
  CapsLock: [XK_Caps_Lock, XK_Caps_Lock, XK_Caps_Lock, XK_Caps_Lock],
  ContextMenu: [XK_Menu, XK_Menu, XK_Menu, XK_Menu],
  Control: [XK_Control_L, XK_Control_L, XK_Control_R, XK_Control_L],
  Delete: [XK_Delete, XK_Delete, XK_Delete, XK_Delete],
  ArrowDown: [XK_Down, XK_Down, XK_Down, XK_Down],
  End: [XK_End, XK_End, XK_End, XK_End],
  Enter: [XK_Return, XK_Return, XK_Return, XK_Return],
  Escape: [XK_Escape, XK_Escape, XK_Escape, XK_Escape],
  Home: [XK_Home, XK_Home, XK_Home, XK_Home],
  Insert: [XK_Insert, XK_Insert, XK_Insert, XK_Insert],
  ArrowLeft: [XK_Left, XK_Left, XK_Left, XK_Left],
  Meta: [XK_Super_L, XK_Super_L, XK_Super_R, XK_Super_L],
  NumLock: [XK_Num_Lock, XK_Num_Lock, XK_Num_Lock, XK_Num_Lock],
  PageDown: [XK_Page_Down, XK_Page_Down, XK_Page_Down, XK_Page_Down],
  PageUp: [XK_Page_Up, XK_Page_Up, XK_Page_Up, XK_Page_Up],
  ArrowRight: [XK_Right, XK_Right, XK_Right, XK_Right],
  Shift: [XK_Shift_L, XK_Shift_L, XK_Shift_R, XK_Shift_L],
  " ": [XK_space, XK_space, XK_space, XK_space],
  Tab: [XK_Tab, XK_Tab, XK_Tab, XK_Tab],
  ArrowUp: [XK_Up, XK_Up, XK_Up, XK_Up],
};

const FIXED_KEYS: Record<string, string> = {
  Backquote: "`",
  Minus: "-",
  Equal: "=",
  BracketLeft: "[",
  BracketRight: "]",
  Backslash: "\\",
  IntlBackslash: "\\",
  Semicolon: ";",
  Quote: "'",
  Comma: ",",
  Period: ".",
  Slash: "/",
  Space: " ",
};

function getKeycode(evt: KeyboardEvent): string {
  if (evt.code) {
    if (evt.code === "OSLeft") return "MetaLeft";
    if (evt.code === "OSRight") return "MetaRight";
    return evt.code;
  }
  return "Unidentified";
}

function getKey(evt: KeyboardEvent): string {
  if (evt.key !== undefined && evt.key !== "Unidentified") {
    if (evt.key === "OS") return "Meta";
    return evt.key;
  }

  const code = getKeycode(evt);
  if (code in FIXED_KEYS) {
    return FIXED_KEYS[code];
  }

  return "Unidentified";
}

export function getRemoteKeysym(evt: KeyboardEvent): number | null {
  const key = getKey(evt);

  if (key === "Unidentified") {
    return null;
  }

  if (key in DOM_KEY_TABLE) {
    let location = evt.location;
    if (location === undefined || location > 3) {
      location = 0;
    }

    if (key === "Meta") {
      const code = getKeycode(evt);
      if (code === "AltLeft") return XK_Super_L;
      if (code === "AltRight") return XK_Super_R;
    }

    if (key === "Clear") {
      const code = getKeycode(evt);
      if (code === "NumLock") return XK_Num_Lock;
    }

    return DOM_KEY_TABLE[key][location];
  }

  if (key.length !== 1) {
    return null;
  }

  const codePoint = key.codePointAt(0);
  return codePoint ?? null;
}

export function charToRemoteKeysym(char: string): number | null {
  if (char === "\n") return XK_Return;
  if (char === "\t") return XK_Tab;
  if (char === "\b") return XK_BackSpace;
  if (char.length === 1) return char.codePointAt(0) ?? null;
  return null;
}

