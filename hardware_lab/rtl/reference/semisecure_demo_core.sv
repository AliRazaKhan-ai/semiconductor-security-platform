module semisecure_demo_core (
    input  logic       clk,
    input  logic       rst_n,
    input  logic       valid_i,
    input  logic [1:0] opcode_i,
    input  logic [7:0] data_i,
    output logic       ready_o,
    output logic [7:0] data_o
);

    function automatic logic [7:0] normal_result(
        input logic [1:0] opcode,
        input logic [7:0] data
    );
        case (opcode)
            2'b00: normal_result = data;
            2'b01: normal_result = data + 8'h01;
            2'b10: normal_result = data ^ 8'h5A;
            default: normal_result = {data[3:0], data[7:4]};
        endcase
    endfunction

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            ready_o <= 1'b0;
            data_o  <= 8'h00;
        end else begin
            ready_o <= valid_i;
            if (valid_i) begin
                data_o <= normal_result(opcode_i, data_i);
            end
        end
    end

endmodule
