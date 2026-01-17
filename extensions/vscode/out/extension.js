"use strict";
var __createBinding = (this && this.__createBinding) || (Object.create ? (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    var desc = Object.getOwnPropertyDescriptor(m, k);
    if (!desc || ("get" in desc ? !m.__esModule : desc.writable || desc.configurable)) {
      desc = { enumerable: true, get: function() { return m[k]; } };
    }
    Object.defineProperty(o, k2, desc);
}) : (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    o[k2] = m[k];
}));
var __setModuleDefault = (this && this.__setModuleDefault) || (Object.create ? (function(o, v) {
    Object.defineProperty(o, "default", { enumerable: true, value: v });
}) : function(o, v) {
    o["default"] = v;
});
var __importStar = (this && this.__importStar) || (function () {
    var ownKeys = function(o) {
        ownKeys = Object.getOwnPropertyNames || function (o) {
            var ar = [];
            for (var k in o) if (Object.prototype.hasOwnProperty.call(o, k)) ar[ar.length] = k;
            return ar;
        };
        return ownKeys(o);
    };
    return function (mod) {
        if (mod && mod.__esModule) return mod;
        var result = {};
        if (mod != null) for (var k = ownKeys(mod), i = 0; i < k.length; i++) if (k[i] !== "default") __createBinding(result, mod, k[i]);
        __setModuleDefault(result, mod);
        return result;
    };
})();
var __importDefault = (this && this.__importDefault) || function (mod) {
    return (mod && mod.__esModule) ? mod : { "default": mod };
};
Object.defineProperty(exports, "__esModule", { value: true });
exports.activate = activate;
exports.deactivate = deactivate;
const vscode = __importStar(require("vscode"));
const axios_1 = __importDefault(require("axios"));
const API_URL = 'http://localhost:5000/api';
const API_KEY = 'local-dev-key-change-in-production';
class KrypticTrackLogger {
    constructor() {
        this.isLogging = true;
        this.currentFile = null;
        this.fileStartTime = 0;
        this.lastActionTime = Date.now();
        this.statusBarItem = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Right, 100);
        this.updateStatusBar();
        this.statusBarItem.show();
        // Track file changes
        vscode.workspace.onDidOpenTextDocument(this.onFileOpen.bind(this));
        vscode.workspace.onDidChangeTextDocument(this.onFileEdit.bind(this));
        vscode.workspace.onDidSaveTextDocument(this.onFileSave.bind(this));
        vscode.workspace.onDidCloseTextDocument(this.onFileClose.bind(this));
        // Track git commits
        vscode.commands.registerCommand('git.commit', () => {
            this.logAction('git_commit', {});
        });
        // Track terminal usage
        vscode.window.onDidChangeActiveTerminal(() => {
            this.logAction('terminal_switch', {});
        });
        // Track debug sessions
        vscode.debug.onDidStartDebugSession(() => {
            this.logAction('debug_start', {});
        });
        vscode.debug.onDidTerminateDebugSession(() => {
            this.logAction('debug_end', {});
        });
        // Periodic status update
        setInterval(() => this.heartbeat(), 30000); // Every 30 seconds
    }
    async logAction(actionType, context) {
        if (!this.isLogging)
            return;
        try {
            await axios_1.default.post(`${API_URL}/log-action`, {
                source: 'vscode',
                action_type: actionType,
                context: context
            }, {
                headers: {
                    'X-API-Key': API_KEY,
                    'Content-Type': 'application/json'
                },
                timeout: 1000
            });
        }
        catch (error) {
            // Silently fail - backend might not be running
            console.error('KrypticTrack: Failed to log action', error);
        }
    }
    onFileOpen(document) {
        if (document.uri.scheme !== 'file')
            return;
        const filePath = document.fileName;
        const language = document.languageId;
        const extension = filePath.split('.').pop() || '';
        this.currentFile = filePath;
        this.fileStartTime = Date.now();
        this.logAction('file_open', {
            file: filePath,
            language: language,
            extension: extension
        });
    }
    onFileEdit(event) {
        if (!this.currentFile || event.document.uri.scheme !== 'file')
            return;
        const changes = event.contentChanges.length;
        const language = event.document.languageId;
        this.logAction('file_edit', {
            file: this.currentFile,
            language: language,
            changes: changes
        });
    }
    onFileSave(document) {
        if (document.uri.scheme !== 'file')
            return;
        const filePath = document.fileName;
        const language = document.languageId;
        const duration = Date.now() - this.fileStartTime;
        const lineCount = document.lineCount;
        this.logAction('file_save', {
            file: filePath,
            language: language,
            duration: duration,
            lines_of_code: lineCount
        });
    }
    onFileClose(document) {
        if (document.uri.scheme !== 'file')
            return;
        const filePath = document.fileName;
        const duration = Date.now() - this.fileStartTime;
        this.logAction('file_close', {
            file: filePath,
            duration: duration
        });
        this.currentFile = null;
    }
    heartbeat() {
        // Log that we're still active
        if (this.isLogging) {
            this.logAction('heartbeat', {
                workspace: vscode.workspace.workspaceFolders?.[0]?.name || 'unknown'
            });
        }
    }
    pause() {
        this.isLogging = false;
        this.updateStatusBar();
        vscode.window.showInformationMessage('KrypticTrack: Logging paused');
    }
    resume() {
        this.isLogging = true;
        this.updateStatusBar();
        vscode.window.showInformationMessage('KrypticTrack: Logging resumed');
    }
    updateStatusBar() {
        if (this.isLogging) {
            this.statusBarItem.text = '$(circle-filled) IRL Logging';
            this.statusBarItem.color = '#00ff00';
        }
        else {
            this.statusBarItem.text = '$(circle-outline) IRL Paused';
            this.statusBarItem.color = '#ff0000';
        }
    }
    dispose() {
        this.statusBarItem.dispose();
    }
}
function activate(context) {
    const logger = new KrypticTrackLogger();
    // Register commands
    const pauseCommand = vscode.commands.registerCommand('kryptictrack.pause', () => {
        logger.pause();
    });
    const resumeCommand = vscode.commands.registerCommand('kryptictrack.resume', () => {
        logger.resume();
    });
    const statusCommand = vscode.commands.registerCommand('kryptictrack.status', async () => {
        try {
            const response = await axios_1.default.get(`${API_URL}/stats`, {
                headers: { 'X-API-Key': API_KEY }
            });
            vscode.window.showInformationMessage(`KrypticTrack: ${response.data.total_actions} actions logged`);
        }
        catch (error) {
            vscode.window.showWarningMessage('KrypticTrack: Backend not available');
        }
    });
    context.subscriptions.push(logger, pauseCommand, resumeCommand, statusCommand);
}
function deactivate() { }
//# sourceMappingURL=extension.js.map