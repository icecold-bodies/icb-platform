// RT9 PowerShell 5.1 sim - the stand-in for ssh.exe and scp.exe (the same program under both names). It is a NATIVE
// program on purpose: Windows PowerShell 5.1 builds a native command line from its arguments and this program's
// runtime splits it again exactly as the C runtime of the real ssh.exe does - so an argument whose double quotes
// PowerShell 5.1 drops (RT8, 21 Oct) arrives here broken too, and the sim shows it. It never reaches a network: it
// writes the arguments it received (NUL-separated) to a request file and hands that file to the WSL forwarder,
// which runs an ssh command inside the fake prod and does an scp copy between the Windows stage and the fake /tmp.
// Fails closed: without RT9_STUB_REQ and RT9_STUB_FWD it refuses (exit 255).
using System;
using System.Diagnostics;
using System.IO;
using System.Text;

public static class Rt9Stub {
    public static int Main(string[] args) {
        string tool = Path.GetFileNameWithoutExtension(System.Reflection.Assembly.GetEntryAssembly().Location).ToLowerInvariant();
        string reqDir = Environment.GetEnvironmentVariable("RT9_STUB_REQ");
        string fwd = Environment.GetEnvironmentVariable("RT9_STUB_FWD");
        if (String.IsNullOrEmpty(reqDir) || String.IsNullOrEmpty(fwd)) {
            Console.Error.WriteLine(tool + " stub: RT9_STUB_REQ / RT9_STUB_FWD not set - refusing");
            return 255;
        }
        if (Environment.GetEnvironmentVariable("RT9_STUB_DOWN") == "1") {
            Console.Error.WriteLine(tool + ": connect to host 127.0.0.9 port 22: Connection timed out");
            return 255;
        }
        string name = tool + "-" + DateTime.Now.ToString("HHmmss") + "-" + Guid.NewGuid().ToString("N").Substring(0, 8);
        string req = Path.Combine(reqDir, name + ".req");
        File.WriteAllText(req, tool + "\0" + String.Join("\0", args), new UTF8Encoding(false));
        File.WriteAllText(req + ".cmdline", Environment.CommandLine, new UTF8Encoding(false));
        string full = Path.GetFullPath(req);
        string wsl = "/mnt/" + Char.ToLowerInvariant(full[0]) + full.Substring(2).Replace('\\', '/');
        ProcessStartInfo psi = new ProcessStartInfo("wsl.exe", "-u root -- bash " + fwd + " " + wsl);
        psi.UseShellExecute = false;
        Process p = Process.Start(psi);
        p.WaitForExit();
        return p.ExitCode;
    }
}
