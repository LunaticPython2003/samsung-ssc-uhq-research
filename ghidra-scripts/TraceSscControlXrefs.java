import ghidra.app.script.GhidraScript;
import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.program.model.address.Address;
import ghidra.program.model.symbol.Reference;
import ghidra.program.model.symbol.ReferenceManager;
import ghidra.program.model.listing.Function;

/**
 * Analyze xrefs from Samsung's SSC bitrate table addresses.
 * Run against the local unmodified libbluetooth_jni.so in Ghidra.
 *
 * Address constants are image-base-specific, observed in the documented
 * Galaxy Z Fold7 build; other firmware images may use different addresses.
 * Writes results only into the local Ghidra headless log.
 */
public class TraceSscControlXrefs extends GhidraScript {
    private static final String[] TABLES = {
        "002077b0", // UHQ2 target bitrates
        "00207600", // legacy / limited target bitrates
        "0020a2d0", // additional table region
        "00209720"  // additional table region
    };

    public void run() throws Exception {
        ReferenceManager manager = currentProgram.getReferenceManager();
        DecompInterface decomp = new DecompInterface();
        decomp.openProgram(currentProgram);
        java.util.HashSet<Address> processed = new java.util.HashSet<>();
        int count = 0;

        for (String offset : TABLES) {
            Address table = toAddr(offset);
            println("\n### TABLE " + table);
            int refs = 0;
            for (Reference r : manager.getReferencesTo(table)) {
                refs++;
                Function caller = getFunctionContaining(r.getFromAddress());
                println("XREF " + r.getFromAddress() +
                    " caller=" + (caller == null ? "unknown" : caller.getName()));
                if (caller == null || processed.contains(caller.getEntryPoint()) || count >= 16) {
                    continue;
                }
                processed.add(caller.getEntryPoint());
                count++;
                DecompileResults result = decomp.decompileFunction(caller, 50, monitor);
                if (result != null && result.decompileCompleted()
                    && result.getDecompiledFunction() != null) {
                    String body = result.getDecompiledFunction().getC();
                    println("DECOMPILED " + caller.getName() +
                        "\n" + body.substring(0, Math.min(body.length(), 20000)));
                } else {
                    println("DECOMPILATION_FAILED " + caller.getName());
                }
            }
            println("TABLE_REFERENCE_COUNT " + table + " " + refs);
        }
        decomp.dispose();
        println("UNIQUE_DECOMPILED_FUNCTIONS " + count);
    }
}
