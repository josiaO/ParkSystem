import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.app.script.GhidraScript;
import ghidra.program.model.data.DataType;
import ghidra.program.model.listing.Data;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.FunctionManager;
import ghidra.program.model.listing.Listing;
import ghidra.program.model.listing.Program;
import ghidra.program.model.data.StringDataInstance;
import ghidra.program.model.symbol.Reference;
import ghidra.program.model.symbol.Symbol;
import ghidra.program.model.symbol.SymbolIterator;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.HashSet;
import java.util.List;
import java.util.Locale;
import java.util.Set;

/** Fresh, evidence-only ParkWatch audit. No prior reverse-engineering report is read. */
public class FreshParkWatchAudit extends GhidraScript {
    private static final List<String> API_KEYWORDS = Arrays.asList(
        "net_", "play_", "dv_", "ipc_", "qy", "nsd", "vz", "lpr", "simplelpr",
        "capture", "startstream", "setcapture", "callback", "pushimage", "getimage"
    );
    private static final List<String> STRING_KEYWORDS = Arrays.asList(
        "ipc_qy", "ocxconfig", "net_", "stream", "video", "capture", "snap", "lpr",
        "plate", "ocr", "recogn", "simplelpr", "callback", "roi", "region", "crop",
        "jpeg", "jpg", "decode", "queue", "thread", "line"
    );

    private boolean interestingApi(String name) {
        String lower = name == null ? "" : name.toLowerCase(Locale.ROOT);
        for (String keyword : API_KEYWORDS) {
            if (lower.contains(keyword)) return true;
        }
        return false;
    }

    private boolean interestingString(String name) {
        String lower = name == null ? "" : name.toLowerCase(Locale.ROOT);
        for (String keyword : STRING_KEYWORDS) {
            if (lower.contains(keyword)) return true;
        }
        return false;
    }

    private boolean interestingFunction(String name) {
        if (name == null) return false;
        String lower = name.toLowerCase(Locale.ROOT);
        return lower.startsWith("dv_") || lower.startsWith("net_") || lower.startsWith("play_") ||
            lower.startsWith("ipc_qy") || lower.startsWith("simplelpr") ||
            lower.contains("lpr_loadapis") || lower.contains("simplelprdev") ||
            lower.contains("startstream") || lower.contains("setcapturecallback");
    }

    private void emitCallers(Symbol symbol, int limit) {
        Reference[] refs = symbol.getReferences();
        int count = 0;
        FunctionManager functions = currentProgram.getFunctionManager();
        for (Reference ref : refs) {
            if (count >= limit) break;
            Function caller = functions.getFunctionContaining(ref.getFromAddress());
            println("  CALLER " + (caller == null ? "<none>" : caller.getName()) +
                " @ " + ref.getFromAddress() + " type=" + ref.getReferenceType());
            count++;
        }
        if (refs.length > limit) println("  CALLER ... truncated ...");
    }

    private void emitFunctionCallers(Function function, int limit) {
        Reference[] refs = getReferencesTo(function.getEntryPoint());
        int count = 0;
        FunctionManager functions = currentProgram.getFunctionManager();
        for (Reference ref : refs) {
            if (count >= limit) break;
            Function caller = functions.getFunctionContaining(ref.getFromAddress());
            if (caller == function) continue;
            println("  FUNCTION_CALLER " + (caller == null ? "<none>" : caller.getName()) +
                " @ " + ref.getFromAddress() + " type=" + ref.getReferenceType());
            count++;
        }
        if (refs.length > limit) println("  FUNCTION_CALLER ... truncated ...");
    }

    private void emitDecompile(Function function) {
        if (function == null) return;
        DecompInterface decompiler = new DecompInterface();
        decompiler.openProgram(currentProgram);
        DecompileResults result = decompiler.decompileFunction(function, 20, monitor);
        if (result != null && result.decompileCompleted() && result.getDecompiledFunction() != null) {
            String text = result.getDecompiledFunction().getC();
            text = text.replace('\n', ' ');
            if (text.length() > 1400) text = text.substring(0, 1400) + " ...";
            println("  DECOMPILE " + function.getName() + " " + text);
        }
        decompiler.dispose();
    }

    @Override
    public void run() throws Exception {
        Program program = currentProgram;
        println("=== FRESH PARKWATCH GHIDRA AUDIT ===");
        println("PROGRAM " + program.getName());
        println("LANGUAGE " + program.getLanguageID() + " COMPILER " + program.getCompilerSpec().getCompilerSpecID());
        println("IMAGE_BASE " + program.getImageBase() + " EXECUTABLE " + program.getExecutablePath());

        SymbolIterator symbols = program.getSymbolTable().getAllSymbols(true);
        List<Symbol> matches = new ArrayList<>();
        Set<String> seen = new HashSet<>();
        Set<Function> apiCallers = new HashSet<>();
        while (symbols.hasNext()) {
            Symbol symbol = symbols.next();
            String name = symbol.getName();
            if (symbol.isExternal()) {
                if (!interestingApi(name)) continue;
            } else if (!interestingFunction(name)) {
                continue;
            }
            String key = symbol.isExternal() + "|" + name + "|" + symbol.getAddress();
            if (seen.add(key)) matches.add(symbol);
        }
        println("INTERESTING_SYMBOL_COUNT " + matches.size());
        for (Symbol symbol : matches) {
            println("SYMBOL " + (symbol.isExternal() ? "EXTERNAL" : "LOCAL") +
                " " + symbol.getName() + " @ " + symbol.getAddress());
            if (symbol.isExternal()) emitCallers(symbol, 40);
            else {
                Function function = program.getFunctionManager().getFunctionAt(symbol.getAddress());
                if (function != null) {
                    emitFunctionCallers(function, 40);
                    for (Reference ref : getReferencesTo(function.getEntryPoint())) {
                        Function caller = program.getFunctionManager().getFunctionContaining(ref.getFromAddress());
                        if (caller != null && caller != function && !caller.isThunk()) apiCallers.add(caller);
                    }
                }
            }
        }

        Listing listing = program.getListing();
        int stringCount = 0;
        for (Data data : listing.getDefinedData(true)) {
            if (stringCount >= 300) break;
            try {
                String value = StringDataInstance.getStringDataInstance(data).getStringValue();
                if (value != null && value.length() >= 4 && interestingString(value)) {
                    String compact = value.replace('\n', ' ').replace('\r', ' ');
                    if (compact.length() > 300) compact = compact.substring(0, 300) + " ...";
                    println("STRING @ " + data.getAddress() + " " + compact);
                    stringCount++;
                }
            } catch (Exception ignored) {
                // A malformed/unsupported data item is not evidence to discard the rest.
            }
        }
        println("INTERESTING_STRING_COUNT " + stringCount);

        FunctionManager functions = program.getFunctionManager();
        int decompiled = 0;
        for (Function function : apiCallers) {
            if (decompiled >= 25) break;
            println("FUNCTION " + function.getName() + " @ " + function.getEntryPoint());
            emitFunctionCallers(function, 40);
            emitDecompile(function);
            decompiled++;
        }
        println("DECOMPILED_INTERESTING_FUNCTIONS " + decompiled);
        println("=== END FRESH PARKWATCH GHIDRA AUDIT ===");
    }
}
