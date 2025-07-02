import * as path from "path";
import * as vscode from "vscode";
import {
  LanguageClient,
  LanguageClientOptions,
  ServerOptions,
} from "vscode-languageclient/node";

let client: LanguageClient;

export function activate(context: vscode.ExtensionContext) {
  // Use NODE_ENV === "development" for debug, otherwise production
  const isDebug = process.env.NODE_ENV === "development";
  let serverOptions: ServerOptions;

  if (isDebug) {
    console.log("Starting SCL server in DEBUG mode");
    serverOptions = {
      command: "python",
      args: ["-m", "scl_server.main"],
      options: {
        cwd: context.asAbsolutePath("server"),
      },
    };
  } else {
    console.log("Starting SCL server in PRODUCTION mode");
    serverOptions = {
      command: context.asAbsolutePath(
        path.join("dist", "server", "server.exe")
      ),
      options: {
        cwd: context.asAbsolutePath("server"),
      },
    };
  }

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

  client.start().then(
    () => {
      console.log("Language Client successfully started.");
    },
    (err) => {
      console.error("Language Client failed to start", err);
    }
  );
}

export function deactivate(): Thenable<void> | undefined {
  return client?.stop();
}
