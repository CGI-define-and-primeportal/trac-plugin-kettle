$(document).ready(function() {
  $("#content").find("h2").addAnchor(_("Link to this section"));

  var executions = 0;
  var executions_loading = false;
  function loadExecutions(specific_elem) {
    executions ++;
    executions_loading = true;
    var results_tables = specific_elem ? $("table", specific_elem) : $(".results-table");
    $(results_tables).each(function(i) {
      var table = $(this);
      var result_url = table.attr("data-url");
      // Load table's contents from URL
      $.ajax({
        url: result_url,
        success: function(data) {
          // Put results in DOM (hidden)
          var updated_contents = $("#ajax-results").html(data);
          // Check revision numbers against one another, update if different
          if($("td.rev", updated_contents).html() != $("td.rev", table).html()) {
            $("tbody", table).html(updated_contents.html());
            if(executions != 1) {
              $("tbody tr td", table).effect({
                duration: 2000,
                effect: "highlight",
                color: "#DFEEFD"
              });
            }
            $("tr td:first-child", table).remove();
            // If we've specified a transform object, clear the timeout and set success status
            if(specific_elem) {
              clearTimeout(specific_elem.data("timeout"));
              specific_elem.data("n", 0);
              $(".execute-actions .btn", specific_elem).removeClass("disabled");
              $(".execute-actions .btn:first", specific_elem).html("<i class='icon-bolt'></i> Execute");
            }
          }
          if((i + 1) == results_tables.length) executions_loading = false;
        },
        error: function() {
          if((i + 1) == results_tables.length) executions_loading = false;
        }
      });
    });
  };

  loadExecutions();
  execution_interval = setInterval(function() { if(!executions_loading) loadExecutions(); }, 20000);

  // Attaches a timeout to the elements data object
  // Also attaches a count which will cause the time in between checks to increase over time
  function throttledUpdates(elem) {
    if(!elem.data("n")) {
      elem.data("n", 1);
      elem.data("interval", 4);
    }
    else {
      elem.data("n", elem.data("n") + 1);
      if(!(elem.data("n") % 10)) {
        elem.data("interval", elem.data("interval") * 2);
      }
      loadExecutions(elem);
    }
    elem.data("timeout", setTimeout(function() { throttledUpdates(elem) }, elem.data("interval") * 1000));
  }

  $("#bi-integration-url-dialog").dialog({autoOpen:false,width:500, modal:true, title:"Report GET URL"});
  $("#content .get-url-btn").click(function(){
    $("#bi-integration-url-placeholder").attr('href', this.href);
    $("#bi-integration-url-placeholder").html(this.href);
    $("#bi-integration-url-dialog").dialog('open');
    return false;
  });

  $("#dialogupload").dialog({autoOpen:false, width:400, modal:true, title:"Upload Transformations"});
  $("#uploadbutton").click(function(){
    $("#dialogupload").dialog('open');
    return false;
  });
  $("#dialogschedule").dialog({autoOpen:false, width:400, modal:true, title:"Schedule Transformations"});
  $("#schedulebutton").click(function(){
    $("#dialogschedule").dialog('open');
    return false;
  });
  // Execution event
  $(".execute-actions a[data-action]").click(function() {
    var transform_name = $(this).closest(".execute-actions").attr("data-transform");
    var transform_wrapper = $("#transform-" + transform_name);
    var execute_btn_handler = $(".execute-actions", transform_wrapper);
    var group_label = $(".group-label", execute_btn_handler);

    if($(".btn.disabled", execute_btn_handler).length == 0) {
      // Set our form values given the execution request
      $("#exec-action").val($(this).attr("data-action"));
      $("#exec-transform").val(transform_name);

      // Change the button state to loading
      group_label.html("<i class='icon-spin icon-spinner'></i>");
      $(".btn", execute_btn_handler).addClass("disabled");

      // If our request is not to async
      if($("#exec-action").val() != "execute_download") {
        $("#exec-form").ajaxSubmit({
          url: $("#exec-form").attr("action"),
          success: function() {
            throttledUpdates(transform_wrapper);
          }
        });
      }
      else {
        setTimeout(function() {
          $(".btn", execute_btn_handler).removeClass("disabled");
          group_label.html("<i class='icon-bolt'></i> Execute");
        }, 30000);
        $("#exec-form").submit();
      }
    }
    execute_btn_handler.removeClass("open");
  });
});