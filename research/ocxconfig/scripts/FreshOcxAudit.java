/*
 * FreshOcxAudit
 *
 * Reproducible, read-only evidence extraction for the supplied OcxConfig
 * PE files.  This script intentionally does not use or modify any existing
 * analysis project; run it with Ghidra's -postScript option against the fresh
 * project created for the audit.
 */
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Data;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.FunctionIterator;
import ghidra.program.model.listing.Listing;
import ghidra.program.model.listing.DataIterator;
import ghidra.program.model.symbol.RefType;
import ghidra.program.model.symbol.Reference;
import ghidra.program.model.symbol.ReferenceIterator;
import ghidra.program.model.symbol.SourceType;
import ghidra.program.model.symbol.Symbol;
import ghidra.program.model.symbol.SymbolIterator;

import java.util.Locale;
import java.util.regex.Pattern;

public class FreshOcxAudit extends GhidraScript {
    private static final Pattern INTERESTING = Pattern.compile(
        "(?i)(rtsp|stream|play|decode|render|display|frame|video|image|jpeg|jpg|h264|h265|" +
        "vehicle|car|plate|license|recogn|alarm|event|callback|report|region|zone|line|rect|" +
        "draw|overlay|window|hwnd|start|stop|open|close|connect|login|snapshot|capture)"
    );

    @Override
    public void run() throws Exception {
        println("=== FRESH GHIDRA OCXCONFIG AUDIT ===");
        println("PROGRAM=" + currentProgram.getName());
        println("IMAGE_BASE=" + currentProgram.getImageBase());
        println("LANGUAGE=" + currentProgram.getLanguageID());
        println("FUNCTION_COUNT=" + currentProgram.getFunctionManager().getFunctionCount());
        dumpExternalSymbols();
        dumpInterestingExternalXrefs();
        dumpInterestingFunctions();
        dumpInterestingStrings();
    }

    private void dumpExternalSymbols() {
        println("-- EXTERNAL_SYMBOLS --");
        SymbolIterator it = currentProgram.getSymbolTable().getExternalSymbols();
        int count = 0;
        while (it.hasNext()) {
            Symbol s = it.next();
            println("EXT " + s.getName() + " @ " + s.getAddress() +
                " source=" + s.getSource().getDisplayString());
            count++;
        }
        println("EXTERNAL_SYMBOL_COUNT=" + count);
    }

    private void dumpInterestingExternalXrefs() {
        println("-- INTERESTING_EXTERNAL_XREFS --");
        SymbolIterator it = currentProgram.getSymbolTable().getExternalSymbols();
        int count = 0;
        while (it.hasNext()) {
            Symbol s = it.next();
            if (!INTERESTING.matcher(s.getName()).find() && !s.getName().startsWith("Net_")) {
                continue;
            }
            ReferenceIterator refs = currentProgram.getReferenceManager().getReferencesTo(s.getAddress());
            int refCount = 0;
            while (refs.hasNext()) {
                Reference ref = refs.next();
                Function f = currentProgram.getFunctionManager().getFunctionContaining(ref.getFromAddress());
                String fn = f == null ? "<no-function>" : f.getName();
                println("CALL " + s.getName() + " from=" + ref.getFromAddress() +
                    " type=" + ref.getReferenceType() + " function=" + fn);
                refCount++;
            }
            if (refCount > 0) {
                println("CALL_COUNT " + s.getName() + "=" + refCount);
                count++;
            }
        }
        println("INTERESTING_EXTERNAL_WITH_XREF_COUNT=" + count);
    }

    private void dumpInterestingFunctions() {
        println("-- INTERESTING_FUNCTIONS --");
        FunctionIterator it = currentProgram.getFunctionManager().getFunctions(true);
        int count = 0;
        while (it.hasNext()) {
            Function f = it.next();
            String name = f.getName();
            if (INTERESTING.matcher(name).find()) {
                println("FUNC " + f.getEntryPoint() + " " + name +
                    " body=" + f.getBody().getNumAddresses() +
                    " callingConvention=" + f.getCallingConventionName());
                count++;
            }
        }
        println("INTERESTING_FUNCTION_COUNT=" + count);
    }

    private void dumpInterestingStrings() {
        println("-- INTERESTING_STRING_XREFS --");
        Listing listing = currentProgram.getListing();
        int count = 0;
        DataIterator dataIterator = listing.getDefinedData(true);
        while (dataIterator.hasNext()) {
            Data data = dataIterator.next();
            Object value = data.getValue();
            if (value == null) {
                continue;
            }
            String text = value.toString().replace('\n', ' ').replace('\r', ' ');
            if (text.length() < 2 || !INTERESTING.matcher(text).find()) {
                continue;
            }
            println("STRING " + data.getAddress() + " " + quote(text));
            ReferenceIterator refs = currentProgram.getReferenceManager().getReferencesTo(data.getAddress());
            int refCount = 0;
            while (refs.hasNext()) {
                Reference ref = refs.next();
                Function f = currentProgram.getFunctionManager().getFunctionContaining(ref.getFromAddress());
                String fn = f == null ? "<no-function>" : f.getName();
                println("  XREF from=" + ref.getFromAddress() + " type=" + ref.getReferenceType() +
                    " function=" + fn);
                refCount++;
            }
            println("  XREF_COUNT=" + refCount);
            count++;
        }
        println("INTERESTING_STRING_COUNT=" + count);
    }

    private String quote(String text) {
        String compact = text.length() > 260 ? text.substring(0, 260) + "..." : text;
        return "\"" + compact.replace("\\", "\\\\").replace("\"", "\\\"") + "\"";
    }
}
