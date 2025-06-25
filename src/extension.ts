import * as path from "path";
import * as vscode from "vscode";
import {
  LanguageClient,
  LanguageClientOptions,
  ServerOptions,
} from "vscode-languageclient/node";

let client: LanguageClient;

export function activate(context: vscode.ExtensionContext) {
  const pythonPath = "python"; // nebo absolutní path k pythonu, pokud potřeba
  const serverScript = context.asAbsolutePath(
    path.join("server", "scl_server", "main.py")
  );

  const serverOptions: ServerOptions = {
    command: pythonPath,
    args: ["-u", serverScript],
    options: {
      cwd: context.extensionPath,
    },
  };

  const clientOptions: LanguageClientOptions = {
    documentSelector: [{ scheme: "file", language: "scl" }],
    outputChannel: vscode.window.createOutputChannel("SCL Language Server"),
  };

  client = new LanguageClient(
    "sclLanguageServer",
    "SCL Language Server",
    serverOptions,
    clientOptions
  );

  client.start();
}

export function deactivate(): Thenable<void> | undefined {
  return client ? client.stop() : undefined;
}
