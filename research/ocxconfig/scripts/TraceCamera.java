// Export call references and decompile the functions that use the camera, video,
// recognition, and gate entry points. Credential literals are redacted.
// @category Research
import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Data;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.Instruction;
import ghidra.program.model.listing.Listing;
import ghidra.program.model.symbol.Reference;
import ghidra.program.model.symbol.ReferenceIterator;
import ghidra.program.model.symbol.Symbol;
import ghidra.program.model.symbol.SymbolIterator;
import java.io.File;
import java.io.PrintWriter;
import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.regex.Pattern;

public class TraceCamera extends GhidraScript {
    static final int MAX_FUNCTIONS = 40;
    static final Pattern INTEREST = Pattern.compile(
        "(?i).*(Net_(Init|UNinit|AddCamera|DelCamera|ConnCamera.*|DisConnCamera|QueryConnState|"
            + "RegImageRecv.*|RegReportMess.*|FindDevice.*|StartVideo|StopVideo|ImageSnap|"
            + "GetJpgBuffer|RegOffLine.*|GateSetup|SetSynTimePeriod|SetHttpPushSetup|SetPushTargetSetup|"
            + "TransRS485HexDataEx)|"
            + "DV_(InitSDK|ReleaseSDK|OpenDevice|CloseDevice|StartStream|Capture|SetCaptureCallback|"
            + "Exec|OpenRS485|WriteRS485|CloseRS485)|"
            + "CAM_(InitSDK|UninitSDK|OpenDevice|CloseDevice|StartStream|StopStream|"
            + "SetCaptureCallback|Capture|Exec|SerialWrite)|"
            + "LPR_(LoadApis|Create|Recognize|RecognizeAll|Release)|"
            + "Play_(Init|UnInit|OpenCamera|CloseCamera|SetRealDataCallBack.*|GetFrameData|GetJpgBuffer)).*");
    static final Pattern CALLEE_HINT = Pattern.compile(
        "(?i).*(send|recv|connect|socket|WSA|Play_|Rtsp|decode|http|snap|gate|image).*");
    static final Pattern SECRET_LINE = Pattern.compile("(?i).*(password|passwd|productkey|secret).*");
    static final Pattern INTERESTING_STRING = Pattern.compile(
        "(?i).*(rtsp://|https?://|IPC_QY|SimpleLPR|DVNET|NetSDK|PlaySdk|DecodeSdk|RtspRecv|\\.dll).*");

    public void run() throws Exception {
        if (getScriptArgs().length < 1) {
            println("usage: TraceCamera <evidence-dir>");
            return;
        }
        File out = new File(getScriptArgs()[0]);
        out.mkdirs();
        String name = currentProgram.getName();
        PrintWriter refs = new PrintWriter(new File(out, name + ".references.txt"));
        PrintWriter summary = new PrintWriter(new File(out, name + ".summary.txt"));
        summary.println("PROGRAM " + name);
        summary.println("PATH " + currentProgram.getExecutablePath());
        summary.println("LANGUAGE " + currentProgram.getLanguageID());
        summary.println("IMAGE_BASE " + currentProgram.getImageBase());

        LinkedHashSet<Function> primary = new LinkedHashSet<Function>();
        SymbolIterator symbols = currentProgram.getSymbolTable().getAllSymbols(true);
        while (symbols.hasNext() && !monitor.isCancelled()) {
            Symbol symbol = symbols.next();
            if (!INTEREST.matcher(symbol.getName()).matches()) {
                continue;
            }
            refs.println("SYMBOL " + symbol.getName() + " " + symbol.getAddress());
            Function own = getFunctionAt(symbol.getAddress());
            if (own != null && !own.isExternal()) {
                primary.add(own);
            }
            ReferenceIterator incoming = currentProgram.getReferenceManager().getReferencesTo(symbol.getAddress());
            while (incoming.hasNext()) {
                Reference reference = incoming.next();
                Function caller = getFunctionContaining(reference.getFromAddress());
                refs.println("  REF " + reference.getFromAddress() + " " + reference.getReferenceType()
                    + " IN " + (caller == null ? "?" : caller.getName() + " @ " + caller.getEntryPoint()));
                if (caller != null && !caller.isExternal()) {
                    primary.add(caller);
                }
            }
        }

        LinkedHashSet<Function> selected = new LinkedHashSet<Function>(primary);
        for (Function function : new ArrayList<Function>(primary)) {
            if (selected.size() >= MAX_FUNCTIONS) {
                break;
            }
            int added = 0;
            for (Function callee : callees(function)) {
                if (selected.size() >= MAX_FUNCTIONS || added >= 4) {
                    break;
                }
                if (callee.isExternal() || callee.isThunk()) {
                    continue;
                }
                if (CALLEE_HINT.matcher(callee.getName()).matches() || callee.getName().startsWith("FUN_")) {
                    selected.add(callee);
                    refs.println("CALLEE " + function.getName() + " -> " + callee.getName() + " @ " + callee.getEntryPoint());
                    added++;
                }
            }
        }
        refs.close();

        int shown = 0;
        Listing listing = currentProgram.getListing();
        ghidra.program.model.listing.DataIterator data = listing.getDefinedData(true);
        while (data.hasNext() && shown < 80 && !monitor.isCancelled()) {
            Data item = data.next();
            if (!item.hasStringValue()) {
                continue;
            }
            String value = item.getDefaultValueRepresentation();
            if (value.length() > 180 || !INTERESTING_STRING.matcher(value).matches()) {
                continue;
            }
            if (SECRET_LINE.matcher(value).matches()) {
                summary.println("STR " + item.getAddress() + " [redacted]");
            } else {
                summary.println("STR " + item.getAddress() + " " + value);
            }
            shown++;
        }

        DecompInterface decompiler = new DecompInterface();
        decompiler.openProgram(currentProgram);
        PrintWriter c = new PrintWriter(new File(out, name + ".decompiled.c"));
        int count = 0;
        for (Function function : selected) {
            if (count >= MAX_FUNCTIONS || monitor.isCancelled()) {
                break;
            }
            summary.println("FUNCTION " + function.getName() + " ENTRY " + function.getEntryPoint());
            for (String call : callNames(function)) {
                summary.println("  CALL " + call);
            }
            c.println("\n/* FUNCTION " + function.getName() + " ENTRY " + function.getEntryPoint() + " */");
            if (function.getBody().getNumAddresses() > 12000) {
                c.println("/* SKIPPED: function body is too large for this pass */");
                continue;
            }
            DecompileResults result = decompiler.decompileFunction(function, 30, monitor);
            if (result.decompileCompleted() && result.getDecompiledFunction() != null) {
                for (String line : result.getDecompiledFunction().getC().split("\n", -1)) {
                    c.println(redact(line));
                }
            } else {
                c.println("/* FAILED: " + result.getErrorMessage() + " */");
            }
            count++;
        }
        c.close();
        decompiler.dispose();
        summary.println("DECOMPILED " + count);
        summary.close();
        println("Exported " + count + " functions for " + name);
    }

    private ArrayList<Function> callees(Function function) {
        ArrayList<Function> found = new ArrayList<Function>();
        LinkedHashSet<Address> seen = new LinkedHashSet<Address>();
        ghidra.program.model.listing.InstructionIterator instructions =
            currentProgram.getListing().getInstructions(function.getBody(), true);
        while (instructions.hasNext()) {
            Instruction instruction = instructions.next();
            for (Reference reference : instruction.getReferencesFrom()) {
                if (!reference.getReferenceType().isCall() || !seen.add(reference.getToAddress())) {
                    continue;
                }
                Function callee = getFunctionAt(reference.getToAddress());
                if (callee != null) {
                    found.add(callee);
                }
            }
        }
        return found;
    }

    private ArrayList<String> callNames(Function function) {
        ArrayList<String> names = new ArrayList<String>();
        for (Function callee : callees(function)) {
            names.add(callee.getName() + " @ " + callee.getEntryPoint());
        }
        return names;
    }

    private String redact(String line) {
        if (SECRET_LINE.matcher(line).matches()) {
            return line.replaceAll("\"(?:\\\\.|[^\"\\\\])*\"", "\"[redacted]\"");
        }
        return line;
    }
}
