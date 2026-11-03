import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.mem.Memory;

public class DumpSscBitrateTables extends GhidraScript {
    public void run() throws Exception {
        Memory m=currentProgram.getMemory();
        for(String addr: new String[]{"002077b0","00207600","0020a2d0","00209720"}) {
            Address a=toAddr(addr);
            println("TABLE @"+addr);
            for(int level=0;level<8;level++) {
                byte[] val=new byte[4];
                try {
                    m.getBytes(a.add(level*4),val);
                    int v=(val[0]&255)|((val[1]&255)<<8)|((val[2]&255)<<16)|((val[3]&255)<<24);
                    println("  index="+level+" decimal="+Integer.toUnsignedString(v)+" hex=0x"+Integer.toHexString(v));
                }catch(Exception e){println("  READ_ERROR "+e.getMessage());break;}
            }
        }
    }
}
