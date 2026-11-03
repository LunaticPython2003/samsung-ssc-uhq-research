import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.lang.Register;
import ghidra.program.model.listing.Instruction;
import java.math.BigInteger;

/** Independent Ghidra Thumb instruction audit, against a private SM-R640 raw binary.
 * Load with processor ARM:LE:32:v8T and BinaryLoader, image base 0.
 */
public class VerifyR640Dispatch extends GhidraScript {
    public void run() throws Exception {
        Register thumb = currentProgram.getProgramContext().getRegister("TMode");
        println("PROGRAM "+currentProgram.getName()+" LANG "+currentProgram.getLanguageID());
        int[][] spans={
          {0x8d968,0x8d996},{0x8d9b8,0x8da2a},
          {0x8afd4,0x8b03a},{0x8b06a,0x8b0da},
          {0x17bbbe,0x17bbd8},{0x17b01c,0x17b050},
          {0x8deac,0x8defa},{0x8e014,0x8e02a},{0x17ac70,0x17ac90}
        };
        for(int[] p:spans) {
            Address start=toAddr(p[0]),end=toAddr(p[1]-2);
            // ARM:LE:32:v8T defaults to Thumb. Setting TMode again after
            // auto-disassembly conflicts with existing instruction context.
            // Read the already decoded instructions without changing context.
            println("\nWINDOW 0x"+Integer.toHexString(p[0])+"..0x"+Integer.toHexString(p[1]));
            for(int ptr=p[0];ptr<p[1];ptr+=2) {
                Address a=toAddr(ptr);
                Instruction ins=currentProgram.getListing().getInstructionAt(a);
                if(ins==null) {
                    try {disassemble(a);} catch(Exception e) { println("DISASM_ERR "+a+" "+e); }
                    ins=currentProgram.getListing().getInstructionAt(a);
                }
                if(ins!=null) {
                   println("  "+ins.getAddress()+": "+ins.toString()+
                            " flow="+ins.getFlowType().toString());
                   ptr+=ins.getLength()-2;
                }
            }
        }
        Address tab=toAddr(0x8d996);
        println("\nTBB_TARGETS from 0x8d996:");
        for(int i=0;i<=0x16;i++) {
            int v=currentProgram.getMemory().getByte(tab.add(i))&255;
            int addr=0x8d996+2*v;
            println("  index "+i+" -> 0x"+Integer.toHexString(addr));
        }
    }
}
