/**
 * Zenith Design Bridge — Figma Plugin
 *
 * This plugin connects to the Zenith backend via WebSocket and receives
 * validated design commands from the AI tool system. It translates those
 * commands into Figma Plugin API calls.
 *
 * Security:
 * - Authenticates via one-time token from Zenith backend
 * - Only executes known, validated command types
 * - Never runs arbitrary code from the AI
 * - Returns structured results for each command
 */

// ── Configuration ───────────────────────────────────────────────────────────
const ZENITH_WS_URL = 'ws://localhost:8005/api/integrations/figma-plugin/ws';
const ZENITH_API_URL = 'http://localhost:8005/api/integrations/figma-plugin';

// ── State ───────────────────────────────────────────────────────────────────
let ws = null;
let authToken = '';
let isConnected = false;

// ── Plugin Entry Point ──────────────────────────────────────────────────────
figma.showUI(__html__, { width: 340, height: 480, themeColors: true });

figma.ui.onmessage = async (msg) => {
  if (msg.type === 'connect') {
    authToken = msg.token || '';
    connectToZenith(authToken);
  } else if (msg.type === 'disconnect') {
    disconnect();
  } else if (msg.type === 'status') {
    figma.ui.postMessage({ type: 'status', connected: isConnected });
  }
};

// ── WebSocket Connection ────────────────────────────────────────────────────

function connectToZenith(token) {
  if (ws) {
    ws.close();
  }

  const url = `${ZENITH_WS_URL}?token=${encodeURIComponent(token)}`;

  try {
    ws = new WebSocket(url);

    ws.onopen = () => {
      isConnected = true;
      figma.ui.postMessage({ type: 'connected' });
      figma.notify('✓ Connected to Zenith');
    };

    ws.onmessage = async (event) => {
      try {
        const data = JSON.parse(event.data);
        await handleMessage(data);
      } catch (err) {
        console.error('Failed to parse message:', err);
      }
    };

    ws.onclose = (event) => {
      isConnected = false;
      figma.ui.postMessage({ type: 'disconnected', reason: event.reason || 'Connection closed' });
      if (event.code !== 1000) {
        figma.notify('⚠ Disconnected from Zenith', { error: true });
      }
    };

    ws.onerror = (err) => {
      isConnected = false;
      figma.ui.postMessage({ type: 'error', message: 'WebSocket connection error' });
      figma.notify('✗ Connection error', { error: true });
    };
  } catch (err) {
    figma.ui.postMessage({ type: 'error', message: err.message });
  }
}

function disconnect() {
  if (ws) {
    ws.close(1000, 'User disconnected');
    ws = null;
  }
  isConnected = false;
}

// ── Message Handler ─────────────────────────────────────────────────────────

async function handleMessage(data) {
  switch (data.type) {
    case 'handshake':
      figma.ui.postMessage({
        type: 'handshake',
        version: data.version,
        commands: data.commands,
      });
      break;

    case 'command':
      await executeCommand(data);
      break;

    case 'pong':
      break;

    default:
      console.warn('Unknown message type:', data.type);
  }
}

// ── Command Execution ───────────────────────────────────────────────────────

const COMMAND_HANDLERS = {
  create_frame: createFrame,
  create_text: createText,
  create_rectangle: createRectangle,
  modify_node: modifyNode,
  rename_node: renameNode,
};

async function executeCommand(data) {
  const { command_id, command_type, params } = data;

  const handler = COMMAND_HANDLERS[command_type];
  if (!handler) {
    sendResult(command_id, false, null, `Unsupported command: ${command_type}`);
    return;
  }

  try {
    figma.ui.postMessage({
      type: 'executing',
      command_id,
      command_type,
      params,
    });

    const result = await handler(params);

    sendResult(command_id, true, result);

    figma.ui.postMessage({
      type: 'completed',
      command_id,
      command_type,
      result,
    });
  } catch (err) {
    sendResult(command_id, false, null, err.message || String(err));
    figma.ui.postMessage({
      type: 'failed',
      command_id,
      command_type,
      error: err.message,
    });
  }
}

function sendResult(commandId, ok, result, error) {
  if (!ws || ws.readyState !== WebSocket.OPEN) return;

  ws.send(JSON.stringify({
    type: ok ? 'result' : 'error',
    command_id: commandId,
    ok,
    result: result || null,
    message: error || '',
  }));
}

// ── Design Command Implementations ─────────────────────────────────────────

function parseColor(hex) {
  if (!hex) return { r: 1, g: 1, b: 1 };
  hex = hex.replace('#', '');
  return {
    r: parseInt(hex.substr(0, 2), 16) / 255,
    g: parseInt(hex.substr(2, 2), 16) / 255,
    b: parseInt(hex.substr(4, 2), 16) / 255,
  };
}

async function createFrame(params) {
  const frame = figma.createFrame();
  frame.name = params.name || 'Frame';
  frame.resize(params.width || 1440, params.height || 900);
  frame.x = params.x || 0;
  frame.y = params.y || 0;

  if (params.fill_color) {
    frame.fills = [{ type: 'SOLID', color: parseColor(params.fill_color) }];
  }

  figma.currentPage.appendChild(frame);
  figma.viewport.scrollAndZoomIntoView([frame]);

  return {
    node_id: frame.id,
    name: frame.name,
    width: frame.width,
    height: frame.height,
  };
}

async function createText(params) {
  const text = figma.createText();

  // Load font
  const fontFamily = params.font_family || 'Inter';
  const fontWeight = params.font_weight || 'Regular';

  // Map weight names to Figma style names
  const weightMap = {
    'Thin': 'Thin',
    'ExtraLight': 'Extra Light',
    'Light': 'Light',
    'Regular': 'Regular',
    'Medium': 'Medium',
    'SemiBold': 'Semi Bold',
    'Bold': 'Bold',
    'ExtraBold': 'Extra Bold',
    'Black': 'Black',
  };

  const style = weightMap[fontWeight] || fontWeight;

  try {
    await figma.loadFontAsync({ family: fontFamily, style });
  } catch {
    // Fallback to Inter Regular
    await figma.loadFontAsync({ family: 'Inter', style: 'Regular' });
  }

  text.characters = params.text || '';
  text.fontSize = params.font_size || 16;

  if (params.width) {
    text.resize(params.width, text.height);
    text.textAutoResize = 'HEIGHT';
  }

  text.x = params.x || 0;
  text.y = params.y || 0;

  if (params.fill_color) {
    text.fills = [{ type: 'SOLID', color: parseColor(params.fill_color) }];
  }

  // Append to parent frame if specified
  if (params.parent_id) {
    const parent = figma.getNodeById(params.parent_id);
    if (parent && 'appendChild' in parent) {
      parent.appendChild(text);
    }
  }

  return {
    node_id: text.id,
    text: text.characters,
    fontSize: text.fontSize,
  };
}

async function createRectangle(params) {
  const rect = figma.createRectangle();
  rect.resize(params.width || 100, params.height || 100);
  rect.x = params.x || 0;
  rect.y = params.y || 0;

  if (params.name) {
    rect.name = params.name;
  }

  if (params.fill_color) {
    rect.fills = [{ type: 'SOLID', color: parseColor(params.fill_color) }];
  }

  if (params.corner_radius) {
    rect.cornerRadius = params.corner_radius;
  }

  if (params.parent_id) {
    const parent = figma.getNodeById(params.parent_id);
    if (parent && 'appendChild' in parent) {
      parent.appendChild(rect);
    }
  }

  return {
    node_id: rect.id,
    name: rect.name,
    width: rect.width,
    height: rect.height,
  };
}

async function modifyNode(params) {
  const node = figma.getNodeById(params.node_id);
  if (!node) throw new Error(`Node not found: ${params.node_id}`);

  if (params.name !== undefined) node.name = params.name;
  if (params.x !== undefined) node.x = params.x;
  if (params.y !== undefined) node.y = params.y;
  if (params.visible !== undefined) node.visible = params.visible;

  if ((params.width || params.height) && 'resize' in node) {
    node.resize(
      params.width || node.width,
      params.height || node.height
    );
  }

  if (params.opacity !== undefined && 'opacity' in node) {
    node.opacity = Math.max(0, Math.min(1, params.opacity));
  }

  if (params.fill_color && 'fills' in node) {
    node.fills = [{ type: 'SOLID', color: parseColor(params.fill_color) }];
  }

  return {
    node_id: node.id,
    name: node.name,
    modified: Object.keys(params).filter(k => k !== 'node_id'),
  };
}

async function renameNode(params) {
  const node = figma.getNodeById(params.node_id);
  if (!node) throw new Error(`Node not found: ${params.node_id}`);
  const oldName = node.name;
  node.name = params.name;
  return { node_id: node.id, old_name: oldName, new_name: params.name };
}
