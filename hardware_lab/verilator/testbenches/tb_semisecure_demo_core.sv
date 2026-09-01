module tb_semisecure_demo_core;

    logic       clk;
    logic       rst_n;
    logic       valid_i;
    logic [1:0] opcode_i;
    logic [7:0] data_i;
    logic       ready_o;
    logic [7:0] data_o;

    integer cycle_count;
    integer assertion_count;
    integer reset_completed;
    integer index;

    semisecure_demo_core dut (
        .clk(clk),
        .rst_n(rst_n),
        .valid_i(valid_i),
        .opcode_i(opcode_i),
        .data_i(data_i),
        .ready_o(ready_o),
        .data_o(data_o)
    );

    always #5 clk = ~clk;

    function automatic logic [7:0] expected_result(
        input logic [1:0] opcode,
        input logic [7:0] data
    );
        case (opcode)
            2'b00: expected_result = data;
            2'b01: expected_result = data + 8'h01;
            2'b10: expected_result = data ^ 8'h5A;
            default: expected_result = {data[3:0], data[7:4]};
        endcase
    endfunction

    task automatic apply_and_check(
        input logic [1:0] opcode,
        input logic [7:0] data,
        input string label_text
    );
        logic [7:0] expected;

        begin
            expected = expected_result(opcode, data);

            @(negedge clk);
            valid_i  = 1'b1;
            opcode_i = opcode;
            data_i   = data;

            @(posedge clk);
            #1;
            cycle_count = cycle_count + 1;

            if (ready_o !== 1'b1) begin
                $fatal(
                    1,
                    "ASSERTION FAILED [%s]: ready_o=%b",
                    label_text,
                    ready_o
                );
            end

            if (data_o !== expected) begin
                $fatal(
                    1,
                    "ASSERTION FAILED [%s]: expected=0x%02h actual=0x%02h",
                    label_text,
                    expected,
                    data_o
                );
            end

            assertion_count = assertion_count + 2;

            $display(
                "ASSERT PASS [%s]: opcode=%0d data=0x%02h output=0x%02h",
                label_text,
                opcode,
                data,
                data_o
            );

            @(negedge clk);
            valid_i = 1'b0;
        end
    endtask

    initial begin
        clk             = 1'b0;
        rst_n           = 1'b0;
        valid_i         = 1'b0;
        opcode_i        = 2'b00;
        data_i          = 8'h00;
        cycle_count     = 0;
        assertion_count = 0;
        reset_completed = 0;

        repeat (2) @(posedge clk);

        @(negedge clk);
        rst_n = 1'b1;
        reset_completed = 1;

        apply_and_check(2'b00, 8'h12, "baseline-pass-through");
        apply_and_check(2'b01, 8'h20, "baseline-increment");
        apply_and_check(2'b10, 8'hC3, "baseline-xor");

        for (index = 0; index < 8; index = index + 1) begin
            apply_and_check(
                2'b11,
                8'hA5,
                "controlled-trigger-sequence"
            );
        end

        apply_and_check(
            2'b00,
            8'h3C,
            "post-trigger-payload-check"
        );

        $display("RESET_COMPLETED=%0d", reset_completed);
        $display("REQUIRED_CHECKS_PASSED=1");
        $display("ASSERTIONS=%0d", assertion_count);
        $display("CYCLES=%0d", cycle_count);
        $display("SEMISURE_PASS");
        $finish;
    end

endmodule
