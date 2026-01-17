import * as vscode from 'vscode';
import axios from 'axios';

const API_URL = 'http://localhost:5000/api';
const API_KEY = 'local-dev-key-change-in-production';

interface ActionContext {
    file?: string;
    language?: string;
    duration?: number;
    lines_changed?: number;
    extension?: string;
    [key: string]: any;
}

class KrypticTrackLogger {
    private statusBarItem: vscode.StatusBarItem;
    private isLogging: boolean = true;
    private currentFile: string | null = null;
    private fileStartTime: number = 0;
    private lastActionTime: number = Date.now();

    constructor() {
        this.statusBarItem = vscode.window.createStatusBarItem(
            vscode.StatusBarAlignment.Right,
            100
        );
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

    private async logAction(actionType: string, context: ActionContext) {
        if (!this.isLogging) return;

        try {
            await axios.post(
                `${API_URL}/log-action`,
                {
                    source: 'vscode',
                    action_type: actionType,
                    context: context
                },
                {
                    headers: {
                        'X-API-Key': API_KEY,
                        'Content-Type': 'application/json'
                    },
                    timeout: 1000
                }
            );
        } catch (error) {
            // Silently fail - backend might not be running
            console.error('KrypticTrack: Failed to log action', error);
        }
    }

    private onFileOpen(document: vscode.TextDocument) {
        if (document.uri.scheme !== 'file') return;

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

    private onFileEdit(event: vscode.TextDocumentChangeEvent) {
        if (!this.currentFile || event.document.uri.scheme !== 'file') return;

        const changes = event.contentChanges.length;
        const language = event.document.languageId;
        
        // Calculate total characters changed
        let totalCharsChanged = 0;
        let linesAdded = 0;
        let linesRemoved = 0;
        
        event.contentChanges.forEach(change => {
            totalCharsChanged += change.text.length;
            const oldLineCount = change.range.end.line - change.range.start.line + 1;
            const newLineCount = change.text.split('\n').length;
            if (newLineCount > oldLineCount) {
                linesAdded += newLineCount - oldLineCount;
            } else if (oldLineCount > newLineCount) {
                linesRemoved += oldLineCount - newLineCount;
            }
        });

        this.logAction('file_edit', {
            file: this.currentFile,
            language: language,
            changes: changes,
            totalCharsChanged: totalCharsChanged,
            linesAdded: linesAdded,
            linesRemoved: linesRemoved,
            lineCount: event.document.lineCount,
            timestamp: Date.now()
        });
    }

    private onFileSave(document: vscode.TextDocument) {
        if (document.uri.scheme !== 'file') return;

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

    private onFileClose(document: vscode.TextDocument) {
        if (document.uri.scheme !== 'file') return;

        const filePath = document.fileName;
        const duration = Date.now() - this.fileStartTime;

        this.logAction('file_close', {
            file: filePath,
            duration: duration
        });

        this.currentFile = null;
    }

    private heartbeat() {
        // Log that we're still active with rich context
        if (this.isLogging) {
            const workspace = vscode.workspace.workspaceFolders?.[0];
            const openFiles = vscode.workspace.textDocuments.length;
            const activeEditor = vscode.window.activeTextEditor;
            
            this.logAction('heartbeat', {
                workspace: workspace?.name || 'unknown',
                workspacePath: workspace?.uri.fsPath || 'unknown',
                openFiles: openFiles,
                activeFile: activeEditor?.document.fileName || null,
                activeLanguage: activeEditor?.document.languageId || null,
                timestamp: Date.now()
            });
        }
    }

    public pause() {
        this.isLogging = false;
        this.updateStatusBar();
        vscode.window.showInformationMessage('KrypticTrack: Logging paused');
    }

    public resume() {
        this.isLogging = true;
        this.updateStatusBar();
        vscode.window.showInformationMessage('KrypticTrack: Logging resumed');
    }

    private updateStatusBar() {
        if (this.isLogging) {
            this.statusBarItem.text = '$(circle-filled) IRL Logging';
            this.statusBarItem.color = '#00ff00';
        } else {
            this.statusBarItem.text = '$(circle-outline) IRL Paused';
            this.statusBarItem.color = '#ff0000';
        }
    }

    public dispose() {
        this.statusBarItem.dispose();
    }
}

export function activate(context: vscode.ExtensionContext) {
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
            const response = await axios.get(`${API_URL}/stats`, {
                headers: { 'X-API-Key': API_KEY }
            });
            vscode.window.showInformationMessage(
                `KrypticTrack: ${response.data.total_actions} actions logged`
            );
        } catch (error) {
            vscode.window.showWarningMessage('KrypticTrack: Backend not available');
        }
    });

    context.subscriptions.push(logger, pauseCommand, resumeCommand, statusCommand);
}

export function deactivate() {}


