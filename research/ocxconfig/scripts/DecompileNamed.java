// Decompile named functions from an already analyzed program. Credential literals are redacted.
// @category Research
import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.app.script.GhidraScript;
import ghidra.program.model.listing.Function;
import ghidra.program.model.symbol.Symbol;
import ghidra.program.model.symbol.SymbolIterator;
import java.io.File;
import java.io.PrintWriter;
import java.util.LinkedHashSet;
import java.util.regex.Pattern;

public class DecompileNamed extends GhidraScript {
    static final Pattern SECRET_LINE = Pattern.compile("(?i).*(password|passwd|productkey|secret).*");

    public void run() throws Exception {
        if (getScriptArgs().length < 2) {
            println("usage: DecompileNamed <evidence-dir> <comma-separated-names>");
            return;
        }
        File out = new File(getScriptArgs()[0]);
        out.mkdirs();
        LinkedHashSet<String> wanted = new LinkedHashSet<String>();
        for (String part : getScriptArgs()[1].split(",")) {
            if (!part.isEmpty()) {
                wanted.add(part);
            }
        }
        LinkedHashSet<Function> selected = new LinkedHashSet<Function>();
        SymbolIterator symbols = currentProgram.getSymbolTable().getAllSymbols(true);
        while (symbols.hasNext() && !monitor.isCancelled()) {
            Symbol symbol = symbols.next();
            if (!wanted.contains(symbol.getName())) {
                continue;
            }
            Function function = getFunctionAt(symbol.getAddress());
            if (function != null && !function.isExternal()) {
                selected.add(function);
            }
        }
        DecompInterface decompiler = new DecompInterface();
        decompiler.openProgram(currentProgram);
        File dest = new File(out, currentProgram.getName() + ".named.c");
        PrintWriter writer = new PrintWriter(dest);
        writer.println("/* PROGRAM " + currentProgram.getName() + " BASE " + currentProgram.getImageBase() + " */");
        for (Function function : selected) {
            writer.println("\n/* FUNCTION " + function.getName() + " ENTRY " + function.getEntryPoint() + " */");
            DecompileResults result = decompiler.decompileFunction(function, 40, monitor);
            if (result.decompileCompleted() && result.getDecompiledFunction() != null) {
                for (String line : result.getDecompiledFunction().getC().split("\n", -1)) {
                    if (SECRET_LINE.matcher(line).matches()) {
                        line = line.replaceAll("\"(?:\\\\.|[^\"\\\\])*\"", "\"[redacted]\"");
                    }
                    writer.println(line);
                }
            } else {
                writer.println("/* FAILED: " + result.getErrorMessage() + " */");
            }
        }
        writer.close();
        decompiler.dispose();
        println("Named decompile wrote " + selected.size() + " functions to " + dest.getName());
    }
}
